"""The negotiation session engine.

One :class:`NegotiationSession` exists per browser session (a cookie, or a
Prolific PID). It owns the scenario, the negmas mechanism, the human's draft
offer, the history, the tools, the Assistant and the autopilot, and pushes
state to every connected browser tab through :class:`hani2.hub.Hub`.

Threading model
---------------
* Every public method may be called from any thread.
* ``self.lock`` (re-entrant) guards session state; hold it only briefly.
* ``self.step_lock`` serialises mechanism stepping. Opponent steps (which may
  call slow LLMs) run in a worker thread and never hold ``self.lock``, so the
  UI, tools and the Assistant stay responsive while the opponent thinks.
* :meth:`run_on_doc` runs a callable under ``self.lock`` — it is what support
  agents use to read or change UI-owned state safely.
* Every session belongs to one study (``self.study_ref``, see
  :mod:`hani2.projects`). Work it hands to other threads (:meth:`submit`,
  :meth:`submit_ui`, timers, :meth:`in_study`) runs bound to that study, so
  settings, scenarios and results resolve for it.
"""

from __future__ import annotations

import contextlib
import math

import os
import random
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from negmas import ContiguousIssue, ContinuousIssue, Outcome, ResponseType, SAOResponse
from negmas.sao import SAOMechanism, SAONegotiator, SAOState

from hani2 import events as ev
from hani2 import information
from hani2 import projects
from hani2 import scenario_store as store
from hani2.recording import recorder as rec
from hani2.agents import DEFAULT_POOL, expand_agents, make_agent, session_agent_override, short_name
from hani2.config import get_env, results_root
from hani2.tool_controller import PANES, ToolController
from hani2.tools import ui

EXECUTOR = ThreadPoolExecutor(max_workers=int(os.environ.get("HANI2_WORKERS", "32")), thread_name_prefix="hani2")

#: Per-session preferences any participant may change.
USER_PREFS: dict[str, Any] = {
    "show_history": True,
    "show_human_offers": True,
    "offer_panel_always_visible": False,
    "last_offer_on_top": False,
    "offer_display": "text",  # text | table
    "font_scale": 1.0,
    # how the Assistant appears when the admin lets the participant choose: panel | persona | both
    "assistant_presentation": None,
    # the Scenario Info tool: the scenario's picture, and the full description opened when a scenario loads
    "show_scenario_picture": True,
    "open_scenario_description": False,
    # how the picture is shown: small | large | watermark (None: the scenario's picture_style, else small)
    "scenario_picture_style": None,
}

#: What a participant may adjust in their own settings (env.json → interface.participant_settings,
#: per layer). Keys of USER_PREFS are gated by the same name; the others are controls of the page.
PARTICIPANT_SETTINGS: dict[str, tuple[str, str]] = {
    "show_history": ("Show the whole history", "Off: only the latest offer stays visible"),
    "show_human_offers": ("Show my offers in the history", ""),
    "last_offer_on_top": ("Newest offer on top", ""),
    "offer_panel_always_visible": ("Keep the offer editor open", ""),
    "offer_display": ("Offers shown as sentences or issue chips", ""),
    "font_scale": ("Text size", ""),
    "show_scenario_picture": ("Show the scenario's picture", "In the Scenario Info tool"),
    "open_scenario_description": ("Open the full scenario description",
                                  "Expanded in the Scenario Info tool when a scenario loads"),
    "scenario_picture_style": ("Scenario picture style",
                               "Small (beside the story), large (above it) or a watermark (behind it)"),
    "device": ("Layout for phone, tablet or desktop", ""),
    "theme": ("Light or dark theme", ""),
    "layout_view": ("Full, simple or focus view", "The layout menu in the header"),
    "assistant_switch": ("Switch the Assistant on and off", ""),
    "assistant_autonomy": ("How much the Assistant may do", "Only lower than the admin's grant"),
    "assistant_abilities": ("The Assistant's abilities", "Only switch off abilities the admin granted"),
    "assistant_delivery": ("Where unprompted Assistant messages appear", ""),
}

#: Defaults of env.json → interface (participant-facing behaviour; layered like every env.json key).
DEFAULT_INTERFACE: dict[str, Any] = {
    "participant_settings": {k: True for k in PARTICIPANT_SETTINGS},
    # defaults of the participant's own settings (USER_PREFS keys; filled in so the console shows them)
    "prefs": {k: v for k, v in USER_PREFS.items() if v is not None},
    "notifications": {"toast_seconds": 6, "center": True},
}

#: How many notifications a session keeps for the notification centre.
MAX_NOTIFICATIONS = 200
#: Where pinned messages go.
PIN_POSITIONS = ("top", "bottom")

#: Per-session settings only admins may change (defaults may be overridden in
#: env.json → "negotiation").
ADMIN_PREFS: dict[str, Any] = {
    "n_steps": 100,
    "time_limit": 300,
    "pend": 0.0,
    "pend_per_second": 0.0,
    "step_time_limit": None,
    "negotiator_time_limit": None,
    "human_index": 1,
    "end_on_no_response": False,
    "allow_text_only_offers": True,
    "allow_text_agent": True,
    "allow_text_human": True,
    "text_only_mode": False,
    "auto_extract": False,
    "auto_generate": False,
    "init_with_best": True,
    "init_with_last": True,
    "allow_tool_switch": True,
    "allow_moving_tools": True,
    "load_existing": True,
    "generate_on_failure": True,
    "predefined_order": True,
    "allow_scenario_selection": False,
    # The scenario set to use (None: HANI2_SCENARIO_SET, then the default set).
    "scenario_set": None,
    # How the participant's role is chosen: auto | index | roles | alternate | random.
    "role_rule": "auto",
    # Preferred roles for the "roles" rule, e.g. ["Tenant", "Buyer"].
    "human_roles": [],
    "show_opponent_type": False,
    "opponent_types": [],
}

#: Set while the Assistant operates a tool (see ``acting_for_agent``).
_AGENT_CONTEXT = threading.local()
#: Who tools are rendered for in this thread (see ``viewing_as``).
_VIEWER = threading.local()


def _in_own_study(fn: Callable) -> Callable:
    """Run a public session method bound to the session's study (for direct callers
    such as tests and headless runs; the server's threads are bound already)."""
    import functools

    @functools.wraps(fn)
    def _run(self, *a, **kw):
        with projects.use_study(self.study_ref):
            return fn(self, *a, **kw)

    return _run

# old names of admin preferences, still accepted
PREF_ALIASES = {"partner_types": "opponent_types", "show_partner_type": "show_opponent_type"}


class HumanPlaceholder(SAONegotiator):
    """The human's seat. Returns the action the session queued for it (or, under
    negotiator-driven autopilot, the driver's decision)."""

    def __init__(self, *args, session: "NegotiationSession | None" = None, driver: SAONegotiator | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = session
        self._driver = driver

    def join(self, *args, **kwargs) -> bool:  # type: ignore[override]
        joined = super().join(*args, **kwargs)
        if joined and self._driver is not None:
            try:
                self._driver.join(*args, **kwargs)
            except Exception as e:  # pragma: no cover
                print(f"[autopilot] driver failed to join: {e}")
                self._driver = None
        return joined

    def propose(self, state, dest=None):  # pragma: no cover - __call__ is used
        return None

    def respond(self, state, source=None):  # pragma: no cover
        return ResponseType.REJECT_OFFER

    def __call__(self, state: SAOState, dest: str | None = None) -> SAOResponse:
        s = self._session
        if s is not None and s.autopilot_active and self._driver is not None:
            response = self._driver(state, dest=dest)
        else:
            response = s.human_action if s is not None else SAOResponse(ResponseType.REJECT_OFFER, None)
        if s is not None:
            s._tools_hook("action_to_execute", response)
            if s.recorder is not None:
                driven = s.autopilot_active and self._driver is not None
                s.recorder.action(response, "autopilot" if driven else getattr(s, "_pending_actor", "human"))
        return response


def _issue_kind(issue) -> str:
    if isinstance(issue, ContinuousIssue):
        return "float"
    if isinstance(issue, ContiguousIssue):
        return "int"
    vals = list(issue.all) if issue.is_discrete() else []
    if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return "number"
    return "category"


def _group_name(raw: Any) -> str:
    """The group a pool setting names when it is exactly one group (``:key`` or a group file's key)."""
    items = [x.strip() for x in raw.split(",")] if isinstance(raw, str) else [str(x).strip() for x in (raw or [])]
    items = [x for x in items if x]
    if len(items) != 1:
        return ""
    t = items[0]
    if t.startswith(":"):
        return t[1:]
    from hani2 import groups

    return t if "." not in t and groups.find_file(groups.OPPONENT, t) is not None else ""


class NegotiationSession:
    def __init__(self, sid: str, user: str, *, study: Any = projects.UNSET, **kwargs: Any):
        """``study``: the study this session belongs to (a :class:`~hani2.projects.StudyRef`,
        ``"project/study"`` or ``None``); default: the current study."""
        self.study_ref: projects.StudyRef | None = (
            projects.current_study() if study is projects.UNSET else projects.parse_ref(study))
        projects.register_session(sid, self.study_ref)
        with projects.use_study(self.study_ref):
            self._init(sid, user, **kwargs)

    def _init(
        self,
        sid: str,
        user: str,
        *,
        mode: str = "main",
        is_admin: bool = False,
        admin_mode: bool = False,
        query: dict[str, Any] | None = None,
        hub: Any = None,
        user_agent: str = "",
        display_name: str | None = None,
        admin_viewer: str | None = None,
    ):
        self.sid = sid
        #: the admin negotiating as a participant in this session (participant view), else None
        self.admin_viewer = admin_viewer
        self.user = user
        self.display_name = display_name or user
        self.mode = mode
        self.is_admin = is_admin
        self.admin_mode = admin_mode or is_admin
        self.query = dict(query or {})
        self.hub = hub
        self.lock = threading.RLock()
        #: UI messages from the browser are applied in order on this executor.
        self.ui_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"hani2-ui-{sid[:12]}")
        self.step_lock = threading.Lock()
        self.created = time.time()
        self.last_seen = time.time()

        self.prefs: dict[str, Any] = dict(USER_PREFS)
        self.admin_prefs: dict[str, Any] = dict(ADMIN_PREFS)
        self.admin_prefs.update(
            {PREF_ALIASES.get(k, k): v for k, v in (get_env("negotiation", {}) or {}).items()}
        )
        self.prefs.update({k: v for k, v in self.interface_policy()["prefs"].items() if k in USER_PREFS})
        self._apply_study_defaults()
        if os.environ.get("HANI2_SCENARIO_SET"):
            self.admin_prefs["scenario_set"] = os.environ["HANI2_SCENARIO_SET"]
        if self.is_admin:
            self.admin_prefs["time_limit"] = None
            self.admin_prefs["show_opponent_type"] = True
        if mode == "guest":
            self.admin_prefs["load_existing"] = str(self.query.get("load_existing", "")).strip().lower() in ("1", "true", "yes", "on")
            self.admin_prefs["predefined_order"] = False

        self.phase = "idle"  # idle | ready | running | ended | questionnaire | finished
        self.round_number = 0
        self.history: list[dict[str, Any]] = []
        self.chat: list[dict[str, Any]] = []
        self.board: str = ""
        #: messages pinned above or below the negotiation ({id, text, position, level, source, dismissible})
        self.pins: list[dict[str, Any]] = []
        #: every notification shown this session, oldest first (the notification centre)
        self.notifications: list[dict[str, Any]] = []
        self._notification_seq = 0
        self.highlights: list[dict[str, Any]] = []
        self.annotations: dict[str, dict[str, Any]] = {}
        self.agent_panels: list[dict[str, Any]] = []
        self.layout: dict[str, Any] = {"view": self.query.get("view") or "full", "sizes": {}}
        self.pending_question: dict[str, Any] | None = None
        self.notice: dict[str, Any] | None = None
        self.questionnaire: dict[str, Any] | None = None
        self.finish_url: str | None = None
        self.finish_text: str | None = None
        self.draft: dict[str, Any] = {}
        self.draft_text: str = ""
        self.thinking = False
        self.deadline: float | None = None
        self.result: dict[str, Any] | None = None
        self.human_action: SAOResponse = SAOResponse(ResponseType.REJECT_OFFER, None)
        self.human_last_offer: Outcome | None = None
        self._trace_seen = 0
        self._timer: threading.Timer | None = None
        #: set by close(); late timer callbacks check it and do nothing
        self.closed = False
        self.autopilot_active = False
        self.autopilot_driver_name: str | None = None
        self.next_opponent: str = ""
        #: who knows what this round (see hani2.information); the default splits nothing
        self.information = information.InformationState()
        #: the opponent group of the current pool / negotiation ("" when not from a group)
        self.opponent_group: str = ""

        user_path = results_root() / user
        if user_path.resolve().parent != results_root().resolve():
            raise ValueError(f"user name {user!r} does not name a folder inside the results folder")
        user_path.mkdir(parents=True, exist_ok=True)
        try:  # make the study's opponent group packages importable
            from hani2.agents import _prime_group_syspaths

            _prime_group_syspaths()
        except Exception:  # pragma: no cover
            pass
        self.ss: dict[str, Any] = {
            "_session": self,
            "user": user,
            "user_path": user_path,
            "is_admin": self.is_admin,
            "mode": mode,
            "results": [],
            "user_agent": user_agent,
            "view_mode": self.layout["view"],
            "view_source": "query" if self.query.get("view") else "default",
            "negotiation_running": False,
        }
        self.ss["actions"] = self._make_actions()
        #: records everything that happens (see :mod:`hani2.recording`)
        self.recorder: rec.SessionRecorder | None = rec.SessionRecorder(self) if rec.enabled() else None
        self._pending_actor = "human"
        self.tool_controller = ToolController(self)
        self.ss["tool_controller"] = self.tool_controller
        self.tools: list = []
        self._tool_states: dict[int, dict[str, Any]] = {}
        self.active_tabs: dict[str, str | None] = {p: None for p in PANES}
        from hani2.tools.registry import build_tools

        self._build_tools = build_tools
        self._added_timings: set[str] = set()
        self._add_tools("always")

        from hani2 import study

        self.study = study.make_study(self)
        from hani2.support_agent.runtime import create_support_agent_for

        #: the Assistant's settings, the choice made from its pool and any error (see hani2.assignment)
        self.assistant_settings: dict | None = None
        self.assistant_choice: Any = None
        self.assistant_error: str | None = None
        ev.start_session_record(sid, user, mode, user_agent=user_agent)
        from hani2.model_chain import SessionModels

        #: the language models this session uses, one per purpose, chosen once (see hani2.model_chain)
        self.models = SessionModels(self)
        self.model_error: str | None = None
        self.support_agent = create_support_agent_for(self)
        if self.support_agent is not None:
            self.models.get("assistant")  # chosen at session start; a missing model shows a banner
        ev.log_event(sid, ev.EventType.SESSION_START, user=user, value={"mode": mode, **self.assistant_attribution()})

    # ------------------------------------------------------------------ #
    # Small helpers                                                       #
    # ------------------------------------------------------------------ #
    @property
    def scenario(self):
        return self.ss.get("scenario")

    @property
    def mechanism(self) -> SAOMechanism | None:
        return self.ss.get("mechanism")

    @property
    def human_index(self) -> int:
        return int(self.ss.get("human_index", self.admin_prefs.get("human_index", 1)))

    @property
    def human_ufun(self):
        return self.ss.get("human_ufun")

    @property
    def issues(self) -> list:
        s = self.scenario
        return list(s.outcome_space.issues) if s is not None else []

    def _apply_study_defaults(self) -> None:
        """The study's / project's defaults (study.yaml, project.yaml) for this session.

        A study's ``study.yaml`` override wins over everything in ``env.json``; a project's
        ``project.yaml`` default wins over the project's and the settings' ``env.json`` but not
        over the study folder's own ``env.json`` (the more specific layer wins)."""
        ref = self.study_ref
        study = projects.get_study(ref) if ref is not None else None
        study_env: dict = {}
        if study is not None:
            from hani2.config import read_json_own_file

            study_env = (read_json_own_file(projects.study_dir(study.ref) / "env.json").get("negotiation") or {})
        for key in ("scenario_set", "role_rule", "human_roles", "time_limit", "n_steps", "information"):
            from_study = study is not None and key in study.overrides
            if not from_study and key in study_env:
                continue  # the study folder's env.json is more specific than project.yaml
            v = projects.setting(key, None, ref=ref)
            if v is not None:
                self.admin_prefs[key] = v
        opp = projects.setting("opponents", None, ref=ref)
        if opp:
            self.admin_prefs["opponent_types"] = [o.strip() for o in opp.split(",")] if isinstance(opp, str) else list(opp)

    def in_study(self, fn: Callable) -> Callable:
        """``fn`` wrapped to run bound to this session's study (for other threads)."""
        return projects.bind(fn, self.study_ref)

    def submit(self, fn: Callable, *args, **kwargs):
        actor = rec.current_actor()

        def _run():
            try:
                with rec.bind(self.sid), projects.use_study(self.study_ref), \
                        rec.acting(actor) if actor else contextlib.nullcontext():
                    return fn(*args, **kwargs)
            except Exception:  # noqa: BLE001
                traceback.print_exc()

        return EXECUTOR.submit(_run)

    def run_on_doc(self, fn: Callable, timeout: float = 30.0):
        """Run ``fn`` under the session lock and return its result."""
        with self.lock:
            return fn()

    def emit(self, msg: dict[str, Any]) -> None:
        if self.hub is not None:
            self.hub.push(self.sid, msg)

    def push_state(self) -> None:
        if self.hub is not None:
            self.hub.push_state(self.sid)

    def toast(self, message: str, level: str = "info", duration: int | None = None, action: dict | None = None,
              source: str = "system") -> bool:
        """A notification that pops up and disappears (``duration`` ms; ``None``: the layer's
        ``interface.notifications.toast_seconds``; 0: stays until dismissed). Every notification
        is also kept for the notification centre. ``source``: ``system`` or ``assistant``."""
        with self.lock:
            self._notification_seq += 1
            note = {"id": self._notification_seq, "message": str(message), "level": level, "source": source,
                    "time": time.time()}
            self.notifications.append(note)
            del self.notifications[:-MAX_NOTIFICATIONS]
        self.emit({"type": "toast", "message": str(message), "level": level, "duration": duration, "action": action,
                   "source": source, "id": note["id"]})
        self.push_state()
        return True

    def clear_notifications(self) -> dict:
        with self.lock:
            self.notifications = []
        self.push_state()
        return {"ok": True}

    # ------------------------------------------------------------------ #
    # Pinned messages                                                     #
    # ------------------------------------------------------------------ #
    def pin(self, text: str, position: str = "top", level: str = "info", pin_id: str | None = None,
            dismissible: bool = True, source: str = "assistant") -> dict:
        """Pin a markdown message above (``top``) or below (``bottom``) the negotiation. The rest
        of the screen shrinks to make room, so nothing is covered. The same ``pin_id`` replaces
        that pin. Returns ``{"ok", "id"}``."""
        text = str(text or "").strip()
        if not text:
            return {"ok": False, "error": "text is required"}
        if position not in PIN_POSITIONS:
            return {"ok": False, "error": "position must be top or bottom"}
        level = level if level in ("info", "success", "warning", "error") else "info"
        with self.lock:
            pid = str(pin_id or f"pin{len(self.pins) + 1}-{uuid.uuid4().hex[:4]}")[:40]
            if source != "briefing" and any(p["id"] == pid and p.get("source") == "briefing" for p in self.pins):
                return {"ok": False, "error": "that pin is the participant's private briefing"}
            item = {"id": pid, "text": text, "position": position, "level": level, "source": source,
                    "dismissible": bool(dismissible)}
            for i, p in enumerate(self.pins):
                if p["id"] == pid:
                    self.pins[i] = item
                    break
            else:
                self.pins.append(item)
                others = [p for p in self.pins if p.get("source") != "briefing"]
                if len(others) > 8:  # drop the oldest; a briefing stays
                    drop = {id(p) for p in others[:-8]}
                    self.pins = [p for p in self.pins if id(p) not in drop]
        self.push_state()
        return {"ok": True, "id": pid}

    def unpin(self, pin_id: str | None = None, *, by: str = "assistant") -> dict:
        """Remove one pin (``None``: every pin). The participant may remove dismissible pins only."""
        with self.lock:
            before = len(self.pins)
            self.pins = [p for p in self.pins if not (
                (pin_id is None or p["id"] == pin_id) and (by != "human" or p["dismissible"])
                and not (by == "assistant" and p.get("source") == "briefing"))]  # the participant's own
            removed = before - len(self.pins)
        if removed:
            self.push_state()
        return {"ok": bool(removed), "removed": removed}

    # ------------------------------------------------------------------ #
    # What the participant may adjust                                     #
    # ------------------------------------------------------------------ #
    def interface_policy(self) -> dict[str, Any]:
        """env.json → ``interface`` as it applies to this session's layer (study > project >
        start-time overrides > settings folder > defaults)."""
        from hani2.config import _deep_merge

        with projects.use_study(self.study_ref):
            raw = get_env("interface", {}) or {}
        pol = _deep_merge(DEFAULT_INTERFACE, raw if isinstance(raw, dict) else {})
        ps = pol.get("participant_settings")
        pol["participant_settings"] = {k: bool((ps or {}).get(k, True)) for k in PARTICIPANT_SETTINGS}
        if not isinstance(pol.get("prefs"), dict):
            pol["prefs"] = {}
        return pol

    def may_adjust(self, key: str, policy: dict | None = None) -> bool:
        """Whether the participant may change ``key`` (a PARTICIPANT_SETTINGS key). Admins may change everything."""
        if self.is_admin:
            return True
        pol = policy or self.interface_policy()
        return bool(pol["participant_settings"].get(key, key not in PARTICIPANT_SETTINGS))

    def assistant_presentation(self) -> dict[str, Any]:
        """How the Assistant appears: ``style`` (panel | persona | both), whether the participant
        chooses (assistant_settings.json → ``presentation``) and whether the persona can be moved."""
        sa = getattr(self, "support_agent", None)
        try:
            from hani2.support_agent.settings import load_assistant_settings

            if sa is not None:
                pres = sa.settings.get("presentation") or {}
            else:
                with projects.use_study(self.study_ref):
                    pres = load_assistant_settings().get("presentation") or {}
        except Exception:  # noqa: BLE001
            pres = {}
        style = str(pres.get("style") or "panel")
        choice = style == "choice"
        if choice:
            style = str(self.prefs.get("assistant_presentation") or pres.get("choice_default") or "panel")
        if style not in ("panel", "persona", "both"):
            style = "panel"
        return {"style": style, "choice": choice, "movable": bool(pres.get("persona_movable", True))}

    # ------------------------------------------------------------------ #
    # Who knows what (hani2.information)                                  #
    # ------------------------------------------------------------------ #
    def _build_information(self, scenario, human_index: int, sdir: str | None, info: dict) -> None:
        """Work out this round's information split (past negotiations, market
        research, which part of the preferences each side knows)."""
        try:
            self.information = information.build_state(
                scenario, human_index=human_index, settings=self.admin_prefs.get("information"),
                scenario_dir=sdir, scenario_info=info, assign_seed=f"{self.user}|{self.round_number}|{sdir or ''}")
        except Exception as e:  # noqa: BLE001 - never stop a round for this
            traceback.print_exc()
            self.information = information.InformationState()
            self.information.warnings.append(f"could not set up the information split: {e}")
        self.ss["information"] = self.information.record()
        # what is private stays with the information state: no opponent, tool or saved copy sees it
        for key in information.PRIVATE_INFO_KEYS:
            (scenario.info or {}).pop(key, None)

    @property
    def anonymous_guest(self) -> bool:
        """A playground or study session without an account of its own (not a signed-in user's ``/play``)."""
        return self.mode == "guest" and not str(self.sid).startswith("play:")

    def sees_totals(self, audience: str) -> bool:
        """Whether ``audience`` (``human`` / ``assistant`` / ``shared``) may see what deals are worth."""
        st = self.information
        if audience == "human":
            return st.human_sees_totals
        if audience == "assistant":
            return st.assistant_sees_totals
        return st.human_sees_totals and st.assistant_sees_totals

    def sees_reserved(self, audience: str) -> bool:
        st = self.information
        if audience == "human":
            return st.human_sees_reserved
        if audience == "assistant":
            return st.assistant_sees_reserved
        return st.human_sees_reserved and st.assistant_sees_reserved

    def shown_utility(self, outcome, audience: str = "human") -> float | None:
        """The human's utility of ``outcome`` when ``audience`` may know it, else ``None``."""
        return self.utility(outcome) if self.sees_totals(audience) else None

    def shown_utility_value(self, value, audience: str = "human"):
        return value if self.sees_totals(audience) else None

    def shown_reserved_value(self, audience: str = "human") -> float | None:
        return self.reserved_value() if self.sees_reserved(audience) else None

    def _shown_history(self) -> list[dict[str, Any]]:
        """The history as the human may see it (no deal values when they may not know them)."""
        if self.sees_totals("human"):
            return list(self.history)
        return [{k: v for k, v in h.items() if k not in ("utility", "below_reserved")} for h in self.history]

    def tool_available(self, tool) -> bool:
        """Whether ``tool`` is offered this round (a tool can depend on the information split)."""
        try:
            return bool(tool.available())
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return True

    def current_viewer(self) -> str:
        """Who a tool is being rendered for in this thread: ``assistant`` (inside
        :meth:`viewing_as`) or ``human``."""
        return getattr(_VIEWER, "who", None) or "human"

    @contextlib.contextmanager
    def viewing_as(self, who: str):
        """Render tools for ``who`` (``assistant`` while the Assistant reads or uses a tool)."""
        prev = getattr(_VIEWER, "who", None)
        _VIEWER.who = who
        try:
            yield
        finally:
            _VIEWER.who = prev

    def tool_private_to_human(self, tool) -> bool:
        """Whether ``tool`` shows the human's private information that the
        Assistant must not read this round (it asks the human instead)."""
        fn = getattr(tool, "private_now", None)
        if callable(fn):
            try:
                return bool(fn())
            except Exception:  # noqa: BLE001 - fail closed
                traceback.print_exc()
                return True
        return bool(getattr(tool, "private_information", False)) and self.information.split

    def _information_client_state(self) -> dict[str, Any] | None:
        st = self.information
        if not st.split:
            return None
        return {"totals_hidden": not st.human_sees_totals, "reserved_hidden": not st.human_sees_reserved,
                "preferences": st.human_prefs, "past_negotiations": len(st.human_past),
                "market_research": st.human_market}

    def _information_note(self, audience: str) -> dict[str, Any]:
        st = self.information
        if audience == "assistant":
            return {**st.describe_split(),
                    "how_to_use": "The participant and you know different things. Call get_private_information for "
                                  "what only you know (and show_past_negotiation for one record). The participant "
                                  "cannot see your share unless you tell them; ask them about theirs."}
        return {"split": True}

    def utility(self, outcome) -> float | None:
        if outcome is None or self.human_ufun is None:
            return None
        try:
            return float(self.human_ufun(tuple(outcome)))
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # The opponent's utility (the Assistant's ``opponent_utility`` oracle) #
    # ------------------------------------------------------------------ #
    def _opponent_role(self) -> str:
        """The opponent's role name (e.g. "seller"); empty when roles are relabelled or unnamed."""
        u = self.opponent_ufun
        name = str(getattr(u, "name", "") or "").strip() if u is not None else ""
        return "" if not name or name.lower() in self.labels else name

    @property
    def opponent_ufun(self):
        """The opponent's utility function (``None`` before a scenario is loaded)."""
        s = self.scenario
        if s is None or not getattr(s, "ufuns", None):
            return None
        try:
            return s.ufuns[1 - self.human_index]
        except Exception:  # noqa: BLE001
            return None

    def opponent_utility(self, outcome) -> float | None:
        u = self.opponent_ufun
        if outcome is None or u is None or any(v is None for v in outcome):
            return None
        try:
            return float(u(tuple(outcome)))
        except Exception:  # noqa: BLE001
            return None

    def opponent_preferences(self, top: int = 8) -> dict[str, Any]:
        """The opponent's preferences as plain data: issue weights and option values for a linear
        additive utility function, else its ``top`` best outcomes."""
        u = self.opponent_ufun
        if u is None:
            return {}
        out: dict[str, Any] = {"reserved_value": float(getattr(u, "reserved_value", 0.0) or 0.0)}
        weights, values = getattr(u, "weights", None), getattr(u, "values", None)
        if weights is not None and values is not None and len(weights) == len(self.issues):
            issues = []
            for issue, w, fn in zip(self.issues, weights, values):
                info: dict[str, Any] = {"name": issue.name, "weight": round(float(w), 4)}
                if _issue_kind(issue) not in ("int", "float") or getattr(issue, "cardinality", 1e9) <= 30:
                    try:
                        info["option_values"] = {
                            str(self.display_outcome({"v": ui.jsonable(v)})["v"]): round(float(fn(v)), 4)
                            for v in list(issue.all)[:30]}
                    except Exception:  # noqa: BLE001
                        pass
                issues.append(info)
            out["kind"] = "linear additive: utility = sum of weight x option value"
            out["issues"] = issues
            return out
        try:
            from itertools import islice

            outcomes = list(islice(self.scenario.outcome_space.enumerate_or_sample(max_cardinality=20_000), 20_000))
            ranked = sorted(outcomes, key=lambda o: -(self.opponent_utility(o) or 0.0))[:top]
            out["best_outcomes"] = [dict(offer=self.display_outcome(self.outcome_to_dict(o)),
                                         utility=self.opponent_utility(o)) for o in ranked]
        except Exception:  # noqa: BLE001
            pass
        return out

    def opponent_context(self) -> dict[str, Any]:
        """What the ``opponent_utility`` oracle adds to the Assistant's view of the negotiation."""
        partner = self.partner_offer()
        draft_t = self.draft_outcome()
        hist = []
        for h in self.history[-14:]:
            if h.get("kind") != "offer":
                continue
            o = self.offer_outcome(h.get("offer"))
            hist.append({"by": "you" if h["by"] == "human" else "partner",
                         "offer": self.display_outcome(h.get("offer")), "opponent_utility": self.opponent_utility(o)})
        return {
            "opponent_preferences": self.opponent_preferences(),
            "partner_offer_opponent_utility": self.opponent_utility(partner),
            "draft_offer_opponent_utility": self.opponent_utility(draft_t) if draft_t else None,
            "history_opponent_utility": hist,
        }

    def offer_outcome(self, values: dict[str, Any] | None):
        """An offer given as ``{issue: value}`` (display names allowed) as an outcome tuple, or ``None``
        when an issue is missing or invalid."""
        if not isinstance(values, dict) or not self.issues:
            return None
        out = []
        for issue in self.issues:
            key = next((k for k in values if self._resolve_issue(k) is issue), None)
            if key is None:
                return None
            v = self._coerce(issue, values[key])
            try:
                if not issue.is_valid(v):
                    return None
            except Exception:  # noqa: BLE001
                return None
            out.append(v)
        return tuple(out)

    @property
    def labels(self) -> dict[str, str]:
        """Display names for side words (``{"human": "You", "agent": "Opponent"}``)
        when relabelling applies (see :mod:`hani2.naming`), else ``{}``."""
        key = id(self.scenario)
        cached = self.__dict__.get("_labels")
        if cached is not None and cached[0] == key:
            return cached[1]
        from hani2.naming import role_labels

        m = role_labels(self)
        if "support_agent" in self.__dict__:  # decided once the agent exists, per scenario
            self._labels = (key, m)
        return m

    def relabel(self, components: Any) -> Any:
        """Tool components as the participant should see them (see :mod:`hani2.naming`)."""
        from hani2.naming import relabel_components

        return relabel_components(components, self.labels)

    def relabel_text(self, text: str | None) -> str | None:
        from hani2.naming import relabel_text

        return relabel_text(text, self.labels)

    def display_outcome(self, d: dict[str, Any] | None) -> dict[str, Any] | None:
        from hani2.naming import relabel_value

        m = self.labels
        if d is None or not m:
            return d
        return {k: relabel_value(v, m) for k, v in d.items()}

    def outcome_to_dict(self, outcome) -> dict[str, Any] | None:
        if outcome is None:
            return None
        return {i.name: ui.jsonable(v) for i, v in zip(self.issues, outcome)}

    # ------------------------------------------------------------------ #
    # How offers are shown (the scenario's OfferDisplay, see hani2.display)
    # ------------------------------------------------------------------ #
    @property
    def offer_display(self):
        from hani2.display import OfferDisplay

        return self.ss.get("outcome_display") or OfferDisplay()

    def offer_context(self, surface: str, *, from_human: bool = False, done: bool = False, outcome=None):
        from hani2.display import OfferContext

        m = self.mechanism
        return OfferContext(
            self.scenario, surface=surface, from_human=from_human, is_done=done,
            role=str(self.ss.get("human_id", "")).replace(" (You)", ""),
            utility=self.shown_utility(outcome, "human") if outcome is not None and all(v is not None for v in outcome)
            else None,
            reserved_value=self.shown_reserved_value("human"), is_my_turn=self.is_my_turn(),
            step=getattr(m.state, "step", None) if m is not None else None,
            opponent_offer=self.outcome_to_dict(self.partner_offer()),
        )

    def _display_call(self, method: str, *args):
        """Call a display method; a failing custom display is reported once and
        the default is used instead, so a broken ``display.py`` never stops a
        negotiation."""
        disp = self.offer_display
        try:
            return getattr(disp, method)(*args)
        except Exception:  # noqa: BLE001
            key = (id(disp), method)
            failed = self.__dict__.setdefault("_display_failures", set())
            if key not in failed:
                failed.add(key)
                print(f"[hani2] {type(disp).__name__}.{method} failed; using the default")
                traceback.print_exc()
            return None

    def outcome_str(self, outcome, from_human: bool = False, done: bool = False) -> str:
        """The offer as one line of text (:meth:`OfferDisplay.text`)."""
        if self.scenario is None:
            return str(outcome)
        ctx = self.offer_context("text", from_human=from_human, done=done, outcome=outcome)
        r = self._display_call("text", ctx.as_dict(outcome), ctx)
        if r is None:
            from hani2.display import OfferDisplay

            try:
                r = OfferDisplay().text(ctx.as_dict(outcome), ctx)
            except Exception:  # noqa: BLE001
                r = str(outcome)
        return str(r)

    def _view(self, components) -> list[dict] | None:
        if not components:
            return None
        if isinstance(components, dict):
            components = [components]
        if not isinstance(components, (list, tuple)) or not all(isinstance(c, dict) for c in components):
            return None
        return self.relabel(ui.jsonable(list(components)))

    def offer_view(self, surface: str, outcome, from_human: bool = False) -> list[dict] | None:
        """Custom components for an offer in the ``history`` or on the
        ``table``, or ``None`` for the default view."""
        if outcome is None or self.scenario is None:
            return None
        ctx = self.offer_context(surface, from_human=from_human, outcome=outcome)
        method = "history" if surface == "history" else "on_table"
        return self._view(self._display_call(method, ctx.as_dict(outcome), ctx))

    def draft_controls(self) -> list[dict] | None:
        """Custom counter-offer controls, or ``None`` for the default editor."""
        if self.scenario is None:
            return None
        ctx = self.offer_context("controls", from_human=True, outcome=self.draft_outcome())
        return self._view(self._display_call("controls", dict(self.draft), ctx))

    def issue_widget(self, name: str) -> str | None:
        if self.scenario is None:
            return None
        try:
            return self.offer_display.widget_for(name, self.offer_context("controls", from_human=True))
        except Exception:  # noqa: BLE001
            return None

    def draft_input(self, name: str, value: Any) -> dict:
        """A custom control changed: an issue name sets that issue, any other
        name goes to :meth:`OfferDisplay.on_input`."""
        if self._resolve_issue(name) is not None:
            return self.set_draft({name: value})
        ctx = self.offer_context("controls", from_human=True, outcome=self.draft_outcome())
        updates = self._display_call("on_input", str(name), value, dict(self.draft), ctx)
        if not updates:
            self.push_draft()
            return {"ok": True, "applied": {}}
        return self.set_draft(dict(updates))

    def draft_action(self, action: str, payload: dict | None = None) -> dict:
        """A button of the custom controls was clicked (:meth:`OfferDisplay.on_action`)."""
        ctx = self.offer_context("controls", from_human=True, outcome=self.draft_outcome())
        updates = self._display_call("on_action", str(action), dict(payload or {}), dict(self.draft), ctx)
        if not updates:
            self.push_draft()
            return {"ok": True, "applied": {}}
        return self.set_draft(dict(updates))

    def push_draft(self, by_agent: bool = False) -> None:
        """Send the draft (and the custom controls drawn from it) to the browser."""
        self.emit({"type": "draft", "draft": self.draft, "utility": self.shown_utility(self.draft_outcome(), "human"),
                   "controls": self.draft_controls(), "by_agent": by_agent})

    # ------------------------------------------------------------------ #
    # Tools                                                               #
    # ------------------------------------------------------------------ #
    def tool_state(self, tool) -> dict[str, Any]:
        return self._tool_states[id(tool)]

    def tool_by_id(self, tid: str):
        for t in self.tools:
            if self._tool_states[id(t)]["id"] == tid:
                return t
        return None

    def _add_tools(self, timing: str) -> None:
        if timing in self._added_timings:
            return
        self._added_timings.add(timing)
        new = self._build_tools(self, timing)
        with self.lock:
            present = {t.name.lower() for t in self.tools}
            new = [(spec, tool) for spec, tool in new if tool.name.lower() not in present]
            for spec, tool in new:
                shift = 0 if spec.at_front else 1000
                # where the tool goes in each view (see hani2.tool_groups); the current view's applies now
                views = {v: dict(pane=p.get("pane", spec.pane), order=int(p.get("order", spec.order)) + shift,
                                 visible=bool(p.get("visible", True)))
                         for v, p in (spec.placement or {}).items()}
                here = views.get(self.layout.get("view") or "full") or dict(pane=spec.pane, order=spec.order + shift,
                                                                             visible=True)
                pane = here["pane"]
                self.tools.append(tool)
                self._tool_states[id(tool)] = dict(
                    id=uuid.uuid4().hex[:10],
                    pane=pane,
                    order=here["order"],
                    visible=here["visible"],
                    enabled=bool(tool.enabled),
                    # only a tool placed differently per view moves when the view changes
                    views=views if len({tuple(sorted(p.items())) for p in views.values()}) > 1 else None,
                )
                try:
                    tool.init(self.ss)
                except Exception:
                    traceback.print_exc()
                if here["visible"] and (spec.at_front or self.active_tabs.get(pane) is None):
                    self.active_tabs[pane] = tool.name
                if timing in ("load", "start", "end") and self.scenario is not None:
                    try:
                        tool.scenario_loaded(self.ss, self.scenario)
                    except Exception:
                        traceback.print_exc()
        self.push_state()

    def _tools_hook(self, hook: str, *args) -> None:
        nmi = None
        m = self.mechanism
        if m is not None:
            try:
                nmi = m.negotiators[self.human_index].nmi
            except Exception:
                nmi = m.nmi
        for t in list(self.tools):
            try:
                if hook == "scenario_loaded":
                    t.scenario_loaded(self.ss, *args)
                elif hook in ("action_to_execute", "action_executed"):
                    getattr(t, hook)(self.ss, nmi, *args)
                elif hook == "draft_changed":
                    fn = getattr(t, "draft_changed", None)
                    if fn:
                        fn(self.ss, *args)
                else:
                    getattr(t, hook)(self.ss, nmi)
            except Exception:
                traceback.print_exc()

    def tool_changed(self, tool) -> None:
        if self.hub is None or id(tool) not in self._tool_states:
            return
        self.hub.tool_changed(self.sid, self._tool_states[id(tool)]["id"])

    def shown_tool_names(self) -> set[str]:
        """Tools the browser can be showing: the active (or first) tab of each
        pane, the active tab of combined tab strips (``all``) and an enlarged
        tool (``max``). Other tools are rendered when their tab is opened."""
        with self.lock:
            names: set[str] = set()
            visible = [t for t in self.tools if self._tool_states[id(t)]["visible"] and self.tool_available(t)]
            for pane in PANES:
                in_pane = sorted((t for t in visible if self._tool_states[id(t)]["pane"] == pane),
                                 key=lambda t: self._tool_states[id(t)]["order"])
                if not in_pane:
                    continue
                active = self.active_tabs.get(pane)
                names.add(active if any(t.name == active for t in in_pane) else in_pane[0].name)
            for key in ("all", "max"):
                if self.active_tabs.get(key):
                    names.add(str(self.active_tabs[key]))
            return names

    def tool_is_shown(self, tid: str) -> bool:
        t = self.tool_by_id(tid)
        return t is not None and t.name in self.shown_tool_names()

    @_in_own_study
    def render_tool(self, tid: str) -> dict[str, Any] | None:
        t = self.tool_by_id(tid)
        if t is None or not self.tool_available(t):
            return None
        st = self.tool_state(t)
        if not st["enabled"] and not t.permanent and self.admin_prefs.get("allow_tool_switch", True):
            return {"id": tid, "view": None}
        return {"id": tid, "view": self.relabel(t.render())}

    @_in_own_study
    def tool_input(self, tid: str, name: str, value: Any) -> None:
        t = self.tool_by_id(tid)
        if t is None:
            return
        try:
            t.on_input(name, value)
        except Exception:
            traceback.print_exc()
        ev.log_event(self.sid, ev.EventType.TOOL_INTERACTION, user=self.user, component=t.name, action=f"input:{name}")

    @_in_own_study
    def tool_action(self, tid: str, action: str, payload: dict[str, Any]) -> None:
        t = self.tool_by_id(tid)
        if t is None:
            return
        try:
            t.on_action(action, payload or {})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            from hani2.connections import llm_error

            self.toast(f"{t.name}: {llm_error(e, admin=self.is_admin, generic='something went wrong.')}", "error")
        ev.log_event(self.sid, ev.EventType.TOOL_INTERACTION, user=self.user, component=t.name, action=action)

    # ------------------------------------------------------------------ #
    # Preferences                                                         #
    # ------------------------------------------------------------------ #
    def set_pref(self, key: str, value: Any) -> bool:
        key = PREF_ALIASES.get(key, key)
        if key == "assistant_presentation":
            if not (self.assistant_presentation()["choice"] or self.is_admin) or value not in ("panel", "persona", "both"):
                return False
        elif key in USER_PREFS and not self.may_adjust(key):
            return False
        elif key == "scenario_picture_style" and value not in (None, "small", "large", "watermark"):
            return False
        with self.lock:
            if key in USER_PREFS:
                self.prefs[key] = value
            elif key in ADMIN_PREFS and self.is_admin:
                self.admin_prefs[key] = value
            else:
                return False
        if key in ("show_scenario_picture", "open_scenario_description", "scenario_picture_style"):
            from hani2.tools.builtin import ScenarioInfoTool

            for t in self.tools:
                if isinstance(t, ScenarioInfoTool):
                    t.refresh()
        self.push_state()
        return True

    # ------------------------------------------------------------------ #
    # Scenario loading                                                    #
    # ------------------------------------------------------------------ #
    @_in_own_study
    def load(self, scenario_type: str | None = None, name: str | None = None) -> None:
        """Load the next scenario (no negotiation is started)."""
        with self.lock:
            if self.phase in ("running", "starting", "questionnaire"):
                return
            if self.study.finished():
                self.phase = "finished"
                self.finish_url = self.study.completion_url()
                self.finish_text = self.study.finish_text()
                self.push_state()
                return
            plan = self.study.plan_round(scenario_type if self.can_choose_scenario() else None, name)
            idx = plan.get("index")
            if idx is None and self.ss.get("fixed_scenario_index") is not None:
                idx = int(self.ss["fixed_scenario_index"])  # simulated trials replay the same task
            if idx is None:
                idx = store.next_index(self.ss["user_path"])
            stype = plan.get("type") or store.pick_type(idx, bool(self.admin_prefs.get("predefined_order", True)),
                                                        self.admin_prefs.get("scenario_set"))
            try:
                scenario, info, sdir = store.load_scenario(
                    stype,
                    idx,
                    load_existing=bool(plan.get("load_existing", self.admin_prefs.get("load_existing", True))),
                    generate_on_failure=bool(self.admin_prefs.get("generate_on_failure", True)),
                    name=plan.get("name"),
                    strict=store.strict_scenarios(self.study_ref),  # a project/study setting, not an admin pref
                )
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self.toast(f"Could not load a scenario: {e}", "error")
                return
            self.round_plan = plan
            self.refresh_assistant(plan)  # a schedule slot or a new ?group= may name another Assistant
            self.ss["is_practice_round"] = bool(plan.get("practice", False))
            # the scenario's evaluation criteria are for evaluation only: keep them out of what the
            # opponent, the Assistant and the browser see (the recording stores them)
            criteria = (scenario.info or {}).get("evaluation")
            if criteria is not None:
                scenario.info = {k: v for k, v in (scenario.info or {}).items() if k != "evaluation"}
            self.ss["scenario_evaluation"] = criteria
            self.ss["scenario"] = scenario
            self.ss["scenario_info"] = info
            self.ss["scenario_dir"] = sdir
            self.ss["outcome_display"] = store.display_for(scenario, sdir)
            hi = store.assign_human(
                scenario,
                rule=str(self.admin_prefs.get("role_rule") or "auto"),
                human_index=int(self.admin_prefs.get("human_index", 1)),
                preferred_roles=list(self.admin_prefs.get("human_roles") or []),
                counter=self.round_number,
            )
            self.ss["human_index"] = hi
            self.ss["human_ufun"] = scenario.ufuns[hi]
            self.ss["human_id"] = f"{scenario.ufuns[hi].name} (You)"
            self._build_information(scenario, hi, sdir, info)
            self.ss["mechanism"] = None
            self.ss["load_at_dt"] = datetime.now()
            self.ss["start_at_dt"] = None
            self.ss["negotiation_running"] = False
            self.ss["human_ended_negotiation"] = False
            self.ss["support_agent_used"] = False
            self.ss["autopilot_used"] = self.autopilot_active
            self.history = []
            self.highlights = []
            self.annotations = {}
            self.result = None
            self.notice = None
            self.questionnaire = None
            self.draft = {}
            self.draft_text = ""
            self.human_last_offer = None
            self.human_action = SAOResponse(ResponseType.REJECT_OFFER, None)
            self.highlights = []
            self.annotations = {}
            self.agent_panels = []
            self.board = ""
            self.pins = []
            self.phase = "ready"
        if self.recorder is not None:
            self.recorder.begin()
            self.recorder.scenario()
        self._add_tools("load")
        self._tools_hook("scenario_loaded", scenario)
        ev.log_event(self.sid, ev.EventType.SCENARIO_LOADED, user=self.user, scenario_id=str(info.get("scenario_name")),
                     value={"information": self.information.record()} if self.information.split else None)
        for w in self.information.warnings:
            if self.is_admin:
                self.toast(f"Information split: {w}", "warning")
        self.push_state()
        # a participant's first round opens the pre-questionnaire (if configured) before anything starts
        if not self.study.maybe_pre_questionnaire():
            self.study.after_load()

    # ------------------------------------------------------------------ #
    # The Assistant: which one, attribution                               #
    # ------------------------------------------------------------------ #
    @_in_own_study
    def refresh_assistant(self, plan: dict | None = None) -> None:
        """Re-resolve the Assistant this session should run (the URL's group, a
        schedule slot, the pool) and swap it in when it changed (between negotiations only)."""
        from hani2 import assignment
        from hani2.support_agent.runtime import create_support_agent_for
        from hani2.support_agent.settings import support_agent_enabled

        if self.phase in ("running", "starting"):
            return
        settings = self.assistant_settings
        if settings is None or not support_agent_enabled(settings, is_admin=self.is_admin):
            return
        try:
            choice = assignment.choose_assistant(self, settings, plan)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return
        cur = self.assistant_choice
        if cur is not None and choice.spec == cur.spec and choice.error == cur.error and \
                (self.support_agent is not None or self.assistant_error):
            cur.group, cur.source, cur.pool = choice.group, choice.source, choice.pool
            return
        self.support_agent = create_support_agent_for(self, choice=choice, settings=settings)
        if self.support_agent is not None and self.autopilot_active:
            try:  # the new Assistant drives the autopilot like the old one did
                from hani2.support_agent import autopilot as ap

                drv = ap.resolve_driver(self, ap.load_autopilot_settings())
                self.support_agent.set_autopilot(not ap.is_negotiator_driver(drv))
            except Exception:  # noqa: BLE001
                traceback.print_exc()
        ev.log_event(self.sid, ev.EventType.SUPPORT_AGENT, user=self.user, component="assistant",
                     action="assistant_changed", value=self.assistant_attribution())

    def ablation_condition(self) -> dict[str, Any]:
        """The experimental condition of this negotiation, as orthogonal axes (recorded in the
        recording's ``start`` record; see :mod:`hani2.evaluation.ablation`):

        * ``assistant`` — ``on`` (an Assistant runs), ``none`` (assigned the no-Assistant arm),
          ``off`` (switched off in the settings) or ``error`` (it failed to start);
        * ``oracle`` — the Assistant has the ``opponent_utility`` capability;
        * ``opponent_info_tools`` — the participant's tools (and so the Assistant through them) may
          show the opponent's utilities (admins, or env.json ``tools.show_opponent_utility``);
        * ``autopilot_driver`` — the driver autopilot would use now (``""`` when not allowed).
        """
        from hani2.assignment import is_no_assistant
        from hani2.config import get_env
        from hani2.support_agent import autopilot as ap
        from hani2.support_agent.capabilities import Capability

        c = self.__dict__.get("assistant_choice")
        sa = self.__dict__.get("support_agent")
        if c is not None and is_no_assistant(c.spec):
            assistant = "none"
        elif sa is not None:
            assistant = "on"
        else:
            assistant = "error" if self.__dict__.get("assistant_error") else "off"
        try:
            oracle = sa is not None and sa.capabilities.has(Capability.OPPONENT_UTILITY)
        except Exception:  # noqa: BLE001
            oracle = False
        try:
            s = ap.load_autopilot_settings()
            driver = (ap.resolve_driver(self, s) or "") if ap.autopilot_allowed(s) else ""
        except Exception:  # noqa: BLE001
            driver = ""
        return dict(assistant=assistant, oracle=bool(oracle),
                    opponent_info_tools=bool(self.is_admin or get_env("tools.show_opponent_utility", False)),
                    autopilot_driver=driver)

    def assistant_attribution(self) -> dict[str, Any]:
        """``assistant``, ``assistant_group``, ``assistant_class``, ``assistant_error`` (results rows,
        events, recordings)."""
        c = self.assistant_choice
        sa = self.__dict__.get("support_agent")
        return dict(
            assistant=(c.spec or "") if c is not None else "",
            assistant_group=(c.group or "") if c is not None else "",
            assistant_source=c.source if c is not None else "",
            assistant_class=f"{type(sa).__module__}.{type(sa).__qualname__}" if sa is not None else "",
            assistant_error=self.__dict__.get("assistant_error") or "",
            assistant_scheduling=(c.scheduling or "") if c is not None else "",
        )

    def can_choose_scenario(self) -> bool:
        return self.is_admin or bool(self.admin_prefs.get("allow_scenario_selection", False))

    # ------------------------------------------------------------------ #
    # Opponents                                                           #
    # ------------------------------------------------------------------ #
    @_in_own_study
    def opponent_pool(self) -> list:
        """The opponents this session may face, first match wins: the page's
        ``?opponents=`` / ``?group=``, ``hani2 --opponents`` (``HANI2_OPPONENTS``),
        the admin session setting ``opponent_types`` (study.yaml / project.yaml
        ``opponents``), ``opponents`` in env.json, else the built-in default pool.
        Old names (``?agents=``, ``HANI2_AGENTS``, ``agents``) are still read.
        :attr:`opponent_group` names the group the pool came from (when it came from one)."""
        # ?opponents= is for admins (also an admin playing ?as_participant=1) and for sessions made in
        # code (hani2.testing); anyone may use ?group=
        admin = bool(self.is_admin or getattr(self, "admin_viewer", None) or self.trust_url_opponents)
        override = session_agent_override(self.query, allow_files=admin, allow_specs=admin)
        if override:
            q = self.query
            raw = (q.get("opponents") or q.get("agents")) if admin else None
            self.opponent_group = _group_name(raw) if raw else str(q.get("group") or "").strip().lstrip(":")
            return override
        cmdline = (os.environ.get("HANI2_OPPONENTS") or os.environ.get("HANI2_AGENTS") or "").strip()
        if cmdline:
            pool = expand_agents(cmdline)
            if pool:
                self.opponent_group = _group_name(cmdline)
                return pool
        pool = expand_agents(self.admin_prefs.get("opponent_types") or [])
        if pool:
            self.opponent_group = _group_name(self.admin_prefs.get("opponent_types"))
            return pool
        env = get_env("opponents", []) or get_env("agents", []) or []
        pool = expand_agents(env)
        self.opponent_group = _group_name(env) if pool else ""
        return pool or list(DEFAULT_POOL)

    partner_pool = opponent_pool  # old name

    #: whether ``?opponents=`` in :attr:`query` is honoured for a non-admin (set for sessions made in code)
    trust_url_opponents = False

    def choose_partner(self) -> str:
        plan = getattr(self, "round_plan", {}) or {}
        if plan.get("partner"):
            if plan.get("opponent_group") is not None:
                self.opponent_group = plan["opponent_group"]
            return plan["partner"]
        if self.admin_mode and self.next_opponent:
            self.opponent_group = ""
            return self.next_opponent
        return random.choice(self.opponent_pool())

    # ------------------------------------------------------------------ #
    # Starting a negotiation                                              #
    # ------------------------------------------------------------------ #
    @_in_own_study
    def start(self) -> None:
        with self.lock:
            if self.phase != "ready" or self.scenario is None:
                return
            self.phase = "starting"
            self.thinking = True
        self.push_state()
        try:
            self._make_mechanism()
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            with self.lock:
                self.phase = "ready"
                self.thinking = False
            self.toast(f"Could not start the negotiation: {e}", "error")
            self.push_state()
            return
        with self.lock:
            self.round_number += 1
            self.phase = "running"
            self.ss["negotiation_running"] = True
            self.ss["start_at_dt"] = datetime.now()
            tl = self.mechanism.nmi.time_limit if self.mechanism else None
            self.deadline = (time.time() + float(tl)) if tl and tl != float("inf") else None
        if self.recorder is not None:
            self.recorder.start()
        self._add_tools("start")
        self._reveal_own_preferences()
        self._pin_briefings()
        self._tools_hook("negotiation_started")
        ev.log_event(self.sid, ev.EventType.SCENARIO_STARTED, user=self.user, scenario_id=self._scenario_name(),
                     value={"partner": self.ss.get("last_partner_type"), "opponent_group": self.ss.get("opponent_group", ""),
                            "opponent_scheduling": self.ss.get("opponent_scheduling", ""),
                            "scenario_scheduling": self.ss.get("scenario_scheduling", ""),
                            **(self.ss.get("assistant_attribution") or {})})
        self._schedule_timeout()
        self._agent_event("negotiation_started")
        self.push_state()
        self._step_to_human(wait=30.0)  # a step of the previous round may still be finishing

    def _pin_briefings(self) -> None:
        """Pin the participant's private briefings above the negotiation (see hani2.information)."""
        st = self.information
        if st.human_only_issues or st.human_only_actions:
            self.pin(f"Only you can {st.decisions_text()} here. Your Assistant can suggest, "
                     "but the decision is yours.", position="top", level="info", pin_id="briefing-control",
                     source="briefing")
        for b in st.briefings_for("human"):
            if b.get("pin"):
                try:
                    self.pin(f"**Your private briefing.** {b['text']}", position="top", level="warning",
                             pin_id=f"briefing-{b['id']}", source="briefing")
                except Exception:  # noqa: BLE001
                    traceback.print_exc()

    def _reveal_own_preferences(self) -> None:
        """When a negotiation starts the participant must see their own
        preferences: bring the Preferences tool to the front of its pane, make
        sure that pane is not collapsed, and tell the browser to reveal it
        (open the tool tray on tablets, switch to Tools on phones, leave the
        focus view)."""
        from hani2.tools.builtin import PreferencesTool

        tool = next((t for t in self.tools if isinstance(t, PreferencesTool)), None)
        if tool is None:
            tool = next((t for t in self.tools if t.name == "Preferences"), None)
        if tool is None:
            return
        with self.lock:
            st = self.tool_state(tool)
            st["visible"] = True
            if not st["enabled"]:
                st["enabled"] = True
                tool.enabled = True
            self.active_tabs[st["pane"]] = tool.name
            self.active_tabs["all"] = tool.name
            region = "side" if st["pane"] == "side" else "tools"
            collapsed = [c for c in (self.layout.get("collapsed") or []) if c != region]
            self.layout["collapsed"] = collapsed
            if self.layout.get("view") == "focus":
                self._switch_view("full")
                st = self.tool_state(tool)
                st["visible"] = True
                self.active_tabs[st["pane"]] = tool.name
                self.active_tabs["all"] = tool.name
            self._reveal_seq = getattr(self, "_reveal_seq", 0) + 1
            self.reveal = {"tool": tool.name, "pane": st["pane"], "seq": self._reveal_seq}
        try:
            tool.refresh()
        except Exception:
            traceback.print_exc()

    def _scenario_name(self) -> str:
        s = self.scenario
        return str(s.outcome_space.name) if s is not None else ""

    def _make_mechanism(self) -> None:
        scenario = self.scenario
        p = self.admin_prefs
        plan = getattr(self, "round_plan", {}) or {}
        hi = self.human_index
        partner = self.choose_partner()
        self.ss["last_partner_type"] = partner if isinstance(partner, str) else getattr(partner, "__name__", str(partner))
        self.ss["opponent_group"] = self.opponent_group
        self.ss["assistant_attribution"] = self.assistant_attribution()
        # the scheduling methods that chose this negotiation's opponent and scenario type ("" when
        # HANI2 did not schedule it: outside a study, admins, guests, test links, an admin's choice)
        self.ss["opponent_scheduling"] = str(plan.get("opponent_scheduling") or "") if plan.get("partner") else ""
        self.ss["scenario_scheduling"] = str(plan.get("scenario_scheduling") or "")
        time_limit = plan.get("time_limit", p.get("time_limit"))
        mech_params = dict(
            n_steps=p.get("n_steps") or None,
            time_limit=float(time_limit) if time_limit else None,
            pend=float(p.get("pend") or 0),
            pend_per_second=float(p.get("pend_per_second") or 0),
            step_time_limit=p.get("step_time_limit") or None,
            negotiator_time_limit=p.get("negotiator_time_limit") or None,
            hidden_time_limit=float("inf"),
            ignore_negotiator_exceptions=True,
            one_offer_per_step=True,
            sync_calls=True,
            end_on_no_response=bool(p.get("end_on_no_response", False)),
        )
        if p.get("allow_text_only_offers", True):
            mech_params["allow_none_with_data"] = True
        scenario.mechanism_params = dict(scenario.mechanism_params or {}) | mech_params
        human_name = f"{scenario.ufuns[hi].name} (You)"
        agent_name = f"{scenario.ufuns[1 - hi].name} (AI)"
        agent = make_agent(
            partner,
            {"name": agent_name, "id": agent_name},
            practice=bool(self.ss.get("is_practice_round")),
            verbose=os.environ.get("HANI2_VERBOSE") == "1",
            models=self.models,
        )
        from hani2.support_agent import autopilot as ap

        driver = ap.make_negotiator_driver(self)
        human = HumanPlaceholder(name=human_name, id=human_name, session=self, driver=driver)
        negotiators = [None, None]
        negotiators[hi] = human
        negotiators[1 - hi] = agent
        m = scenario.make_session(negotiators=negotiators)
        self._trace_seen = 0
        self.ss["mechanism"] = m
        self.ss["human_id"] = human.id
        self.ss["human_ufun"] = scenario.ufuns[hi]
        self.ss["autopilot_driver"] = driver
        try:
            from hani2 import llm_logging

            if llm_logging.enabled():
                llm_logging.install()
                llm_logging.attach_mechanism(m, self.ss["user_path"] / "llm_logs" / f"{m.id}.jsonl")
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------------ #
    # Stepping                                                            #
    # ------------------------------------------------------------------ #
    def is_my_turn(self) -> bool:
        m = self.mechanism
        if m is None or m.state.done or self.phase != "running":
            return False
        try:
            return m.next_negotitor_ids()[0] == self.ss.get("human_id")
        except Exception:
            return False

    def _record_new_trace(self) -> None:
        m = self.mechanism
        if m is None:
            return
        trace = m.full_trace
        human_id = self.ss.get("human_id")
        new = trace[self._trace_seen :]
        self._trace_seen = len(trace)
        for row in new:
            t, rel, step, neg, offer, responses, state, text, data = (list(row) + [None] * 9)[:9]
            by_human = str(neg) == str(human_id)
            if by_human and not self.prefs.get("show_human_offers", True):
                continue
            if not by_human and not self.admin_prefs.get("allow_text_agent", True):
                text = None
            extra = {}
            if isinstance(data, dict):
                extra = {k: ui.jsonable(v) for k, v in data.items() if k not in ("text",)}
            util = self.utility(offer)
            self.history.append(
                dict(
                    id=len(self.history),
                    kind="offer",
                    by="human" if by_human else "agent",
                    name=str(neg),
                    offer=self.outcome_to_dict(offer),
                    offer_str=self.relabel_text(self.outcome_str(offer, by_human)) if offer is not None else None,
                    view=self.offer_view("history", offer, by_human),
                    text=self._shown_text(text, data, by_human),
                    data=extra or None,
                    utility=util,
                    below_reserved=(util is not None and util < self.reserved_value()),
                    step=int(step) if step is not None else None,
                    relative_time=float(rel) if rel is not None else None,
                    time=time.time(),
                )
            )
        if new:
            self.emit({"type": "history", "items": self._shown_history()})

    def reserved_value(self) -> float:
        try:
            return float(getattr(self.human_ufun, "reserved_value", 0.0) or 0.0)
        except Exception:
            return 0.0

    def partner_offer(self) -> Outcome | None:
        m = self.mechanism
        if m is None:
            return None
        st = m.state
        if st.current_offer is None:
            return None
        if str(st.current_proposer) == str(self.ss.get("human_id")):
            return None
        return st.current_offer

    def partner_data(self) -> dict | None:
        m = self.mechanism
        if m is None or self.partner_offer() is None:
            return None
        return getattr(m.state, "current_data", None)

    def act(self, response: SAOResponse, on_accepted: Callable[[], None] | None = None) -> bool:
        """Queue the human's response and advance in the background.

        ``on_accepted`` runs under the lock only once the action is taken, so a refused
        action (not the human's turn, double click) changes and logs nothing."""
        with self.lock:
            if not self.is_my_turn() or self.thinking:
                return False
            if on_accepted is not None:
                on_accepted()
            self.thinking = True
            self.highlights = []
            self._pending_actor = self._actor()
        self.push_state()
        self.submit(self._advance, response)
        return True

    def _advance(self, response: SAOResponse) -> None:
        if not self.step_lock.acquire(blocking=False):
            return
        try:
            m = self.mechanism
            if m is None or m.state.done:
                return
            self.human_action = response
            with rec.llm_role("opponent"):
                m.step()
            with self.lock:
                self._record_new_trace()
            self._tools_hook("action_executed", response)
        finally:
            self.step_lock.release()
        # finish (or continue) outside the step lock, so a new round can start right away
        if m.state.done:
            self._finish()
            return
        self._step_to_human()

    def _step_to_human(self, wait: float | None = None) -> None:
        """Step the opponent until it is the human's turn. ``wait`` seconds to
        wait for a step in progress (``None``: skip if one is running)."""
        if not (self.step_lock.acquire(timeout=wait) if wait else self.step_lock.acquire(blocking=False)):
            return
        try:
            m = self.mechanism
            if m is None:
                return
            with self.lock:
                self.thinking = True
            self.push_state()
            human_id = self.ss.get("human_id")
            while not m.state.done and m.next_negotitor_ids()[0] != human_id:
                with rec.llm_role("opponent"):
                    m.step()
                with self.lock:
                    self._record_new_trace()
            with self.lock:
                if not m.state.done:
                    # fill the counter-offer fields before the turn is visible as ours
                    self._init_draft()
                self.thinking = False
        finally:
            self.step_lock.release()
        if m.state.done:
            self._finish()
            return
        self._on_human_turn()

    def _on_human_turn(self) -> None:
        with self.lock:
            self._init_draft()
        if self.recorder is not None:
            self.recorder.turn()
        self._tools_hook("action_requested")
        self.push_state()
        self._agent_event("action_requested")
        if self.autopilot_active and self.ss.get("autopilot_driver") is not None:
            from hani2.support_agent import autopilot as ap

            delay = float(ap.load_autopilot_settings().get("step_delay", 0.0) or 0.0)

            def _go():
                if delay > 0:
                    time.sleep(delay)
                if self.autopilot_active and self.is_my_turn():
                    self.act(SAOResponse(ResponseType.REJECT_OFFER, None))

            self.submit(_go)

    def _init_draft(self) -> None:
        """Initial values of the counter-offer fields: last human offer, else the
        human's best outcome."""
        if self.draft and all(i.name in self.draft for i in self.issues):
            return
        outcome = None
        if self.admin_prefs.get("init_with_last", True) and self.human_last_offer is not None:
            outcome = self.human_last_offer
        elif self.admin_prefs.get("init_with_best", True) and self.human_ufun is not None \
                and self.information.human_sees_totals:
            try:
                outcome = self.human_ufun.best()
            except Exception:
                outcome = None
        if outcome is None and self.scenario is not None:
            outcome = tuple(
                (i.min_value if hasattr(i, "min_value") and _issue_kind(i) in ("int", "float") else list(i.all)[0])
                for i in self.issues
            )
        self.draft = self.outcome_to_dict(outcome) or {}

    # ------------------------------------------------------------------ #
    # Human actions                                                       #
    # ------------------------------------------------------------------ #
    def draft_outcome(self) -> Outcome | None:
        if not self.issues:
            return None
        try:
            return tuple(self._coerce(i, self.draft.get(i.name)) for i in self.issues)
        except Exception:
            return None

    def _coerce(self, issue, value):
        kind = _issue_kind(issue)
        if value is None:
            return None
        if self.labels and isinstance(value, str):
            from hani2.naming import unlabel_value

            value = unlabel_value(value, self.labels)
        try:
            if kind == "int":
                return int(round(float(value)))
            if kind == "float":
                return float(value)
            if kind == "number":
                for v in issue.all:
                    if float(v) == float(value):
                        return v
                return value
            for v in issue.all:
                if str(v) == str(value):
                    return v
        except (TypeError, ValueError, OverflowError):
            return value
        return value

    @_in_own_study
    def set_draft(self, values: dict[str, Any], *, by_agent: bool = False) -> dict:
        if (refused := self._agent_gate("fill_offer")) is not None:
            return refused
        applied, missing, kept = {}, [], []
        agent = self._actor() == "agent"
        with self.lock:
            for key, value in (values or {}).items():
                issue = self._resolve_issue(key)
                if issue is None:
                    missing.append(key)
                    continue
                if agent and self.information.human_only_issue(issue.name):
                    kept.append(issue.name)  # only the participant may set it (hani2.information)
                    continue
                v = self._coerce(issue, value)
                try:
                    valid = bool(issue.is_valid(v))
                except Exception:
                    valid = False
                if not valid:
                    missing.append(f"{key} (invalid value {value!r})")
                    continue
                self.draft[issue.name] = ui.jsonable(v)
                applied[issue.name] = ui.jsonable(v)
        util = self.utility(self.draft_outcome())
        self.emit({"type": "draft", "draft": self.draft, "utility": util if self.sees_totals("human") else None,
                   "controls": self.draft_controls(),
                   "by_agent": by_agent})
        if self.recorder is not None and applied:
            # by_agent means "filled in from outside the editor" (a tool or the assistant);
            # who actually did it is the acting thread's actor
            self.recorder.draft(self.draft, self._actor(), util, via="tool" if by_agent else "editor")
        self._tools_hook("draft_changed", dict(self.draft))
        sa = self.support_agent
        if sa is not None and not by_agent:
            try:
                sa.on_draft_changed(dict(self.draft))
            except Exception:
                traceback.print_exc()
        out = {"ok": not missing, "applied": applied, "unrecognised": missing}
        if kept:
            out["human_only"] = kept
            out["note"] = (f"only the participant may set {', '.join(kept)}; suggest a value to them instead "
                           "(their current values were kept)")
        return out

    def set_draft_text(self, text: str, *, by_agent: bool = False) -> dict:
        if (refused := self._agent_gate("fill_text")) is not None:
            return refused
        if not self.admin_prefs.get("allow_text_human", True):
            return {"ok": False, "error": "no message field (text is disabled)"}
        with self.lock:
            changed = self.draft_text != (text or "")
            self.draft_text = text or ""
        if by_agent:
            self.emit({"type": "draft_text", "text": self.draft_text})
        if self.recorder is not None and changed and (by_agent or self._actor() != "human"):
            self.recorder.draft(self.draft, self._actor(), None, text=self.draft_text,
                                via="tool" if by_agent else "editor")
        return {"ok": True}

    def _resolve_issue(self, key: str):
        k = str(key)
        for pred in (
            lambda i: i.name == k,
            lambda i: i.name.lower() == k.lower(),
            lambda i: k.lower() in i.name.lower() or i.name.lower() in k.lower(),
        ):
            for i in self.issues:
                if pred(i):
                    return i
        return None

    @_in_own_study
    def accept(self) -> bool:
        if self._agent_gate("accept") is not None:
            return False
        offer = self.partner_offer()
        if offer is None:
            return False
        def logged():
            ev.log_event(self.sid, ev.EventType.OFFER_ACCEPTED, user=self.user, scenario_id=self._scenario_name(),
                         utility_value=self.utility(offer), round_number=self.mechanism.state.step if self.mechanism else None)

        return self.act(SAOResponse(ResponseType.ACCEPT_OFFER, offer), logged)

    @_in_own_study
    def end(self) -> bool:
        if self._agent_gate("end") is not None:
            return False
        def ended():
            self.ss["human_ended_negotiation"] = True
            ev.log_event(self.sid, ev.EventType.NEGOTIATION_ENDED, user=self.user, action="end_by_human")

        return self.act(SAOResponse(ResponseType.END_NEGOTIATION, None), ended)

    @_in_own_study
    def send_counter(self, text: str | None = None, offer: dict | None = None, text_only: bool | None = None) -> dict:
        """Send the counter-offer (the draft offer plus the message)."""
        if (refused := self._agent_gate("submit_counter")) is not None:
            return refused
        if offer:
            self.set_draft(offer)
        if text is not None:
            self.set_draft_text(text)
        p = self.admin_prefs
        # the study's setting decides for participants; only an admin may switch it per message
        text_only = bool(p.get("text_only_mode")) if text_only is None or not self.is_admin else bool(text_only)
        msg = (self.draft_text or "").strip() if p.get("allow_text_human", True) else ""
        extract = p.get("auto_extract") and not text_only and msg
        generate = p.get("auto_generate") and not text_only and not msg
        if extract or generate:
            # the model may take seconds: call it without the lock (the interface stays responsive)
            # and use the result only if the turn, offer and message are still the ones it was made for
            state = lambda: (self.round_number, self._trace_seen, dict(self.draft), self.draft_text)  # noqa: E731
            with self.lock:
                before = state()
            extracted = None
            if extract:
                try:
                    from hani2.llm_service import extract_outcome_from_text

                    extracted = extract_outcome_from_text(msg, self.issues, context=self.llm_context()).outcome
                except Exception:
                    traceback.print_exc()
            if generate:
                msg = self._llm_generate_text() or ""
            with self.lock:
                if state() != before:
                    return {"ok": False, "error": "The offer or message changed while it was being prepared. "
                                                  "Check it and send again."}
                if extracted is not None:
                    self.set_draft(self.outcome_to_dict(extracted) or {})
                return self._send_prepared(msg, text_only)
        return self._send_prepared(msg, text_only)

    def _send_prepared(self, msg: str, text_only: bool) -> dict:
        p = self.admin_prefs
        if text_only and not msg:
            return {"ok": False, "error": "Write a message to send in text-only mode."}
        if text_only:
            data = {"text": msg} if msg else None
            outcome = None
        else:
            outcome = self.draft_outcome()
            if outcome is None or any(v is None for v in outcome):
                return {"ok": False, "error": "Fill every issue before sending."}
            try:
                valid = bool(self.scenario.outcome_space.is_valid(outcome))
            except Exception:
                valid = False
            if not valid:
                return {"ok": False, "error": "This offer is not valid in this scenario. Check every issue."}
            data = {"text": msg} if p.get("allow_text_human", True) else None
        def sent():
            self.human_last_offer = outcome if outcome is not None else self.human_last_offer
            self.draft_text = ""
            ev.log_event(self.sid, ev.EventType.COUNTER_OFFER, user=self.user, scenario_id=self._scenario_name(),
                         value={"offer": self.outcome_to_dict(outcome), "text": msg}, utility_value=self.utility(outcome))

        ok = self.act(SAOResponse(ResponseType.REJECT_OFFER, outcome, data), sent)
        return {"ok": ok} if ok else {"ok": False, "error": "It is not your turn."}

    def _llm_generate_text(self) -> str | None:
        try:
            from hani2.llm_service import generate_text_from_outcome

            res = generate_text_from_outcome(self.draft_outcome(), self.issues, context=self.llm_context())
            return None if res.error else res.text
        except Exception:
            traceback.print_exc()
            return None

    def llm_context(self):
        from hani2.llm_service import NegotiationContext

        hist = [
            {"role": "You" if h["by"] == "human" else "Opponent", "text": h.get("text") or "", "outcome": str(h.get("offer") or "")}
            for h in self.history[-10:]
        ]
        return NegotiationContext(
            issues=self.issues,
            outcome_space=self.scenario.outcome_space if self.scenario else None,
            ufun=self.human_ufun if self.information.human_sees_totals else None,
            history=hist or None,
            current_offer=self.partner_offer(),
            models=self.models,
        )

    def extract_offer_from_text(self) -> dict:
        from hani2.llm_service import extract_outcome_from_text

        res = extract_outcome_from_text(self.draft_text or "", self.issues, context=self.llm_context())
        if res.error:
            from hani2.connections import llm_error

            return {"ok": False, "error": llm_error(res.error, admin=self.is_admin)}
        if res.outcome is None:
            return {"ok": False, "error": "No offer found in the message."}
        return self.set_draft(self.outcome_to_dict(res.outcome) or {})

    def generate_text(self) -> dict:
        txt = self._llm_generate_text()
        if not txt:
            return {"ok": False, "error": "Could not generate text (is the LLM configured?)"}
        self.set_draft_text(txt, by_agent=True)
        return {"ok": True, "text": txt}

    # ------------------------------------------------------------------ #
    # Timeout                                                             #
    # ------------------------------------------------------------------ #
    def _schedule_timeout(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self.deadline is None or self.closed:
            return
        delay = max(0.0, self.deadline - time.time()) + 0.25
        self._timer = threading.Timer(delay, self.in_study(self._on_timeout))
        self._timer.daemon = True
        self._timer.start()

    def _on_timeout(self) -> None:
        if self.closed or self.phase != "running":
            return
        if self.autopilot_active:
            self._schedule_timeout()
            return
        if self.is_my_turn() and not self.thinking:
            self.toast("Time's up!", "warning")
            self.act(SAOResponse(ResponseType.REJECT_OFFER, self.human_last_offer))
        else:
            # the opponent's own step will notice the timeout; check again shortly
            self.deadline = time.time() + 2
            self._schedule_timeout()

    # ------------------------------------------------------------------ #
    # Ending                                                              #
    # ------------------------------------------------------------------ #
    def _finish(self) -> None:
        m = self.mechanism
        if m is None:
            return
        with self.lock:
            if self.phase not in ("running", "starting") or getattr(self, "_finishing", False):
                return
            self._finishing = True
            self.thinking = False
            self.ss["negotiation_running"] = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._record_new_trace()
        try:
            row, summary = __import__("hani2.results", fromlist=["save_result"]).save_result(self.ss, m)
            self.ss["results"].append(row)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            row = None
            summary = {"status": "erred", "agent_error": str(e), "n_human_actions": 0, "ended_by": "",
                       "agent_failed": False, "human_utility": None, "agent_utility": None, "human_advantage": None}
        if self.recorder is not None:
            self.recorder.finish(row, summary)
        st = m.state
        agreement = st.agreement
        with self.lock:
            self.phase = "ended"
            self.result = dict(
                summary,
                agreement=self.outcome_to_dict(agreement),
                agreement_str=self.outcome_str(agreement, done=True) if agreement is not None else None,
                step=st.step,
                relative_time=st.relative_time,
                reserved_value=self.reserved_value(),
            )
            if agreement is not None:
                msg = f"Agreement reached: {self.result['agreement_str']}"
            elif summary.get("agent_failed"):
                msg = "The AI agent failed; the negotiation ended without agreement."
            elif st.timedout:
                msg = "The negotiation timed out without agreement."
            elif summary.get("ended_by") == "human":
                msg = "You ended the negotiation without agreement."
            elif summary.get("ended_by") == "agent":
                msg = "Your opponent ended the negotiation without agreement."
            else:
                msg = "The negotiation ended without agreement."
            self.history.append(dict(id=len(self.history), kind="system", text=msg, status=summary.get("status"), time=time.time()))
            # the study's end-of-round step (notice, questionnaire, finish link) happens
            # before anyone can see or act on the ended round
            try:
                self.study.after_round(summary)
            finally:
                self._finishing = False
            self.emit({"type": "history", "items": self._shown_history()})
        self._add_tools("end")
        self._tools_hook("negotiation_ended")
        ev.log_event(self.sid, ev.EventType.NEGOTIATION_ENDED, user=self.user, scenario_id=self._scenario_name(),
                     value={k: ui.jsonable(v) for k, v in summary.items()}, utility_value=summary.get("human_utility"))
        self._agent_event("negotiation_ended")
        self.push_state()

    # ------------------------------------------------------------------ #
    # Assistant bridge                                                #
    # ------------------------------------------------------------------ #
    def _agent_event(self, name: str) -> None:
        sa = self.support_agent
        if sa is None:
            return
        if name == "action_requested" and self.autopilot_active and sa.autopilot:
            from hani2.support_agent import autopilot as ap

            delay = float(ap.load_autopilot_settings().get("step_delay", 0.0) or 0.0)
            with rec.acting("autopilot"):
                self.submit(sa.autopilot_step, delay)
            return
        nmi = None
        try:
            nmi = self.mechanism.negotiators[self.human_index].nmi if self.mechanism else None
        except Exception:
            pass
        with rec.acting("agent"):
            self._track_agent(self.submit(sa.on_event, name, nmi))

    def _track_agent(self, future) -> None:
        """Remember queued Assistant work so tests can wait for it."""
        with self.lock:
            pending = self.__dict__.setdefault("_agent_futures", set())
            pending.add(future)
        future.add_done_callback(lambda f: self.__dict__.get("_agent_futures", set()).discard(f))

    def agent_work_pending(self) -> bool:
        return any(not f.done() for f in list(self.__dict__.get("_agent_futures", ())))

    @_in_own_study
    def user_chat(self, text: str) -> None:
        """The participant typed in the assistant chat (gated by the on/off switch)."""
        sa = self.support_agent
        text = (text or "").strip()
        if sa is None or not text:
            return
        if sa._pending_question is not None:
            sa._answer_question(text, echo=True)
            return
        self.add_chat("You", text)
        if not sa.user_enabled:
            sa.post("(The assistant is turned off. Switch it on to chat.)")
            return
        ev.log_event(self.sid, ev.EventType.SUPPORT_AGENT, user=self.user, component="SupportAgent",
                     action="user_message", value={"actor": "human", "text": text[:500]})
        with rec.acting("agent"):
            sa.handle_user_message(text)

    def add_chat(self, user: str, text: str, *, kind: str = "text", extra: dict | None = None) -> dict:
        msg = dict(id=uuid.uuid4().hex[:8], user=user, text=text, kind=kind, time=time.time(), **(extra or {}))
        with self.lock:
            self.chat.append(msg)
            self.chat = self.chat[-300:]
        self.emit({"type": "chat", "message": msg})
        if self.recorder is not None:
            self.recorder.chat(msg)
        return msg

    # ------------------------------------------------------------------ #
    # The action API shared by the UI and the Assistant                #
    # ------------------------------------------------------------------ #
    def context(self, audience: str = "assistant") -> dict[str, Any]:
        """The live negotiation snapshot for ``audience``: ``assistant`` (the
        default: what the Assistant's language model reads), ``human`` or
        ``shared`` (a tool both see: only what both may know). Utilities and the
        value on disagreement are left out for a party that may not know them
        (see :mod:`hani2.information`)."""
        m = self.mechanism
        st = m.state if m is not None else None
        partner = self.partner_offer()
        draft_t = self.draft_outcome()

        def _issue_info(i):
            info: dict[str, Any] = {"name": i.name}
            if self.information.human_only_issue(i.name):
                info["only_the_participant_may_set"] = True
            if _issue_kind(i) in ("int", "float"):
                info["min"], info["max"] = ui.jsonable(i.min_value), ui.jsonable(i.max_value)
            else:
                try:
                    info["values"] = [self.display_outcome({"v": v})["v"] for v in ui.jsonable(list(i.all))]
                except Exception:
                    pass
            return info

        history = [
            {
                "by": "you" if h["by"] == "human" else "partner",
                "offer": self.display_outcome(h.get("offer")),
                "message": h.get("text"),
                "utility": self.shown_utility_value(h.get("utility"), audience),
            }
            for h in self.history[-14:]
            if h.get("kind") == "offer"
        ]
        return {
            "issues": [_issue_info(i) for i in self.issues],
            "partner_offer": self.display_outcome(self.outcome_to_dict(partner)),
            "partner_offer_utility": self.shown_utility(partner, audience),
            "partner_message": self.relabel_text((self.partner_data() or {}).get("text"))
            if isinstance(self.partner_data(), dict) else None,
            "draft_offer": self.display_outcome(dict(self.draft)),
            "draft_offer_utility": self.shown_utility(draft_t, audience)
            if draft_t and all(v is not None for v in draft_t) else None,
            "draft_message": self.draft_text,
            "reserved_value": self.shown_reserved_value(audience),
            "is_my_turn": self.is_my_turn(),
            "phase": self.phase,
            "step": getattr(st, "step", None),
            "n_steps": getattr(getattr(m, "nmi", None), "n_steps", None),
            "relative_time": getattr(st, "relative_time", None),
            "time_left": max(0.0, self.deadline - time.time()) if self.deadline else None,
            "history": history,
            "result": self.result,
            "tools": [t.name for t in self.tools if self.tool_available(t)],
            **({"information": self._information_note(audience)} if self.information.split else {}),
            **({"names": "Values are shown with these names: "
                         + ", ".join(f"{v} = {'the participant' if k == 'human' else 'the opponent'}"
                                     for k, v in self.labels.items())
                         + ". Use these names with the participant and in offers. The message to the opponent is "
                           "read by the opponent, so there say who gets what in plain words (for example "
                           "'I get the compass, you get the rope')."} if self.labels else {}),
        }

    def _make_actions(self) -> dict[str, Callable]:
        def highlight(key: str, message: str | None = None, **kw):
            return self.highlight(key, message=message, **kw)

        gate = self._agent_gate
        return {
            "set_offer": lambda outcome: gate("fill_offer") or self.set_draft(outcome, by_agent=True),
            "set_text": lambda text: gate("fill_text") or self.set_draft_text(text, by_agent=True),
            "get_offer": lambda: dict(self.draft),
            "get_partner_offer": self.partner_offer,
            "can_act": self.is_my_turn,
            "context": self.context,
            "highlight": lambda *a, **kw: gate("highlight") or highlight(*a, **kw),
            "accept": lambda confirm=True: gate("accept") or (self.request_confirm("accept") if confirm else self.accept()),
            "end": lambda confirm=True: gate("end") or (self.request_confirm("end") if confirm else self.end()),
            "reject_counter": lambda: gate("submit_counter") or self.send_counter(),
        }

    def _actor(self) -> str:
        """Who is acting on the participant's seat in this thread: ``human``
        (a browser message), ``agent`` (the Assistant or a tool working for
        it) or ``autopilot``."""
        if getattr(_AGENT_CONTEXT, "caps", None) is not None:
            return "agent"
        return rec.current_actor() or "human"

    def _agent_gate(self, capability: str) -> dict | None:
        """While the Assistant operates a tool (:meth:`acting_for_agent`),
        refuse what the agent itself may not do; ``None`` means allowed."""
        action = {"submit_counter": "send", "accept": "accept", "end": "end"}.get(capability)
        st = self.information
        human_only = action in st.human_only_actions or (action in ("send", "accept") and bool(st.human_only_issues))
        if action and human_only and self._actor() == "agent":
            return {"ok": False, "human_only": True,
                    "error": f"only the participant may {action} in this negotiation; suggest it to them instead"}
        caps = getattr(_AGENT_CONTEXT, "caps", None)
        if caps is None or capability in caps:
            return None
        return {"ok": False, "error": f"the Assistant is not allowed to do this ({capability} is off)"}

    @contextlib.contextmanager
    def acting_for_agent(self, capabilities: set[str]):
        """Run tool callbacks on behalf of the Assistant: actions the tool
        triggers through the session are limited to ``capabilities``."""
        prev = getattr(_AGENT_CONTEXT, "caps", None)
        _AGENT_CONTEXT.caps = set(capabilities)
        try:
            yield
        finally:
            _AGENT_CONTEXT.caps = prev

    # -- tools added while the session runs -----------------------------------
    def add_tool(self, tool: Any, *, pane: str | None = None, at_front: bool = True, focus: bool = True,
                 by: str = "agent", enabled: bool = True) -> dict:
        """Add a tool now (a :class:`~hani2.tools.base.Tool` subclass or
        instance). It catches up on the scenario and a running negotiation,
        and stays for the rest of the session. ``by`` records who added it."""
        from hani2.tools.base import Tool

        try:
            inst = tool(self.ss, enabled=enabled) if isinstance(tool, type) else tool
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return {"ok": False, "error": f"could not create the tool: {e}"}
        if not isinstance(inst, Tool):
            return {"ok": False, "error": "not a hani2 Tool"}
        name = inst.name or type(inst).__name__
        pane = pane or inst.pane
        if pane not in PANES:
            return {"ok": False, "error": f"pane must be one of {', '.join(PANES)}"}
        with self.lock:
            existing = next((t for t in self.tools if t.name.lower() == name.lower()), None)
            if existing is not None:
                if type(existing) is not type(inst):
                    return {"ok": False, "error": f"another tool is already called {name!r}"}
                st = self.tool_state(existing)
                st["visible"] = True
                if focus:
                    self.active_tabs[st["pane"]] = existing.name
                    self.active_tabs["all"] = existing.name
                inst = None
            else:
                in_pane = [self.tool_state(t)["order"] for t in self.tools if self.tool_state(t)["pane"] == pane]
                order = (min(in_pane, default=0) - 1) if at_front else (max(in_pane, default=0) + 1)
                self.tools.append(inst)
                self._tool_states[id(inst)] = dict(id=uuid.uuid4().hex[:10], pane=pane, order=order, visible=True,
                                                   enabled=bool(inst.enabled), added_by=by)
        if inst is None:
            self.push_state()
            existing.refresh()
            return {"ok": True, "tool": existing.name, "pane": self.tool_state(existing)["pane"], "already_present": True}
        try:
            inst.init(self.ss)
            if self.scenario is not None:
                inst.scenario_loaded(self.ss, self.scenario)
            if self.phase == "running" and self.mechanism is not None:
                try:
                    nmi = self.mechanism.negotiators[self.human_index].nmi
                except Exception:
                    nmi = self.mechanism.nmi
                inst.negotiation_started(self.ss, nmi)
        except Exception:
            traceback.print_exc()
        if focus:
            with self.lock:
                self.active_tabs[pane] = inst.name
                self.active_tabs["all"] = inst.name
        ev.log_event(self.sid, "tool_added", user=self.user, component=inst.name, value={"by": by, "pane": pane})
        self.push_state()
        inst.refresh()
        return {"ok": True, "tool": inst.name, "pane": pane}

    def remove_tool(self, name: str, *, by: str = "agent") -> dict:
        """Remove a tool that was added while the session ran (built-in and
        configured tools can only be hidden)."""
        with self.lock:
            t = next((x for x in self.tools if x.name.lower() == str(name).strip().lower()), None)
            if t is None:
                return {"ok": False, "error": f"no tool named {name!r}"}
            st = self.tool_state(t)
            if not st.get("added_by"):
                return {"ok": False, "error": f"{t.name} was not added during the session; hide it instead"}
            self.tools.remove(t)
            self._tool_states.pop(id(t), None)
            for k, v in list(self.active_tabs.items()):
                if v == t.name:
                    self.active_tabs[k] = None
        ev.log_event(self.sid, "tool_removed", user=self.user, component=t.name, value={"by": by})
        self.push_state()
        return {"ok": True, "tool": t.name}

    def request_confirm(self, kind: str, message: str | None = None) -> dict:
        """Open the accept / end confirmation dialog for the human to approve."""
        self.emit({"type": "confirm", "kind": kind, "message": message})
        return {"ok": True, "status": "confirmation_requested", "action": kind}

    # -- highlighting, annotations, layout, agent panels ------------------
    def highlight(self, target: str, message: str | None = None, style: str = "pulse",
                  duration: float | None = None, by: str = "agent") -> dict:
        """Spotlight a UI element (see :data:`hani2.session.ANCHORS`)."""
        h = dict(id=uuid.uuid4().hex[:8], target=str(target), message=message, style=style,
                 duration=duration, by=by, time=time.time())
        with self.lock:
            self.highlights = [x for x in self.highlights if x["target"] != h["target"]] + [h]
        self.push_state()
        return {"ok": True, "highlighted": target}

    def clear_highlights(self, target: str | None = None) -> dict:
        with self.lock:
            self.highlights = [x for x in self.highlights if target is not None and x["target"] != target]
        self.push_state()
        return {"ok": True}

    def annotate(self, target: str, text: str | None, kind: str = "info") -> dict:
        """Attach a short note to an element (e.g. ``issue:Price``). ``text=None`` removes it."""
        with self.lock:
            if text:
                self.annotations[str(target)] = {"text": str(text), "kind": kind}
            else:
                self.annotations.pop(str(target), None)
        self.push_state()
        return {"ok": True}

    def set_layout(self, **changes: Any) -> dict:
        """Change the interface layout: ``view`` (full | simple | focus),
        ``sizes`` (region → fraction of its container, as set by dragging the
        dividers: ``tools`` (tool column width), ``upper`` (upper tools' share of
        the column), ``dock`` (offer area's share of the height), ``side``
        (offer generators' share of the offer row), ``assistant``; tablets use
        ``tablet_tools``, ``tablet_dock`` and ``tray``; a missing key means the
        default size), ``collapsed`` (list of region names)."""
        allowed = {"view", "sizes", "collapsed", "history_side"}
        with self.lock:
            for k, v in changes.items():
                if k in allowed and v is not None:
                    if k == "view" and v not in ("full", "simple", "focus"):
                        return {"ok": False, "error": "view must be full, simple or focus"}
                    if k == "sizes":
                        if not isinstance(v, dict):
                            return {"ok": False, "error": "sizes must map region names to fractions"}
                        clean = {}
                        for name, frac in v.items():
                            try:
                                f = float(frac)
                            except (TypeError, ValueError):
                                continue
                            if math.isfinite(f) and 0.05 <= f <= 0.95:
                                clean[str(name)[:32]] = round(f, 3)
                        v = clean
                    if k == "collapsed":
                        if not isinstance(v, (list, tuple)):
                            return {"ok": False, "error": "collapsed must be a list of region names"}
                        v = [str(x)[:32] for x in v][:32]
                    if k == "view":
                        self._switch_view(v)
                        continue
                    self.layout[k] = v
            self.ss["view_mode"] = self.layout.get("view")
        self.push_state()
        return {"ok": True, "layout": dict(self.layout)}

    def _switch_view(self, view: str) -> None:
        """Change ``layout["view"]`` and move every tool to its place in the new
        view (see :mod:`hani2.tool_groups`). Where the participant moved or hid a
        tool is remembered per view. Call with the lock held."""
        old = self.layout.get("view") or "full"
        self.layout["view"] = view
        self.ss["view_mode"] = view
        if view == old:
            return
        moved = False
        for t in self.tools:
            st = self._tool_states.get(id(t))
            views = (st or {}).get("views")
            if not views:
                continue
            views[old] = dict(pane=st["pane"], order=st["order"], visible=st["visible"])
            nxt = views.get(view)
            if nxt is None:
                continue
            st["pane"], st["order"], st["visible"] = nxt["pane"], nxt["order"], nxt["visible"]
            moved = True
        if not moved:
            return
        for pane in PANES:
            active = self.active_tabs.get(pane)
            if active is not None and not any(
                    t.name == active and self._tool_states[id(t)]["pane"] == pane and self._tool_states[id(t)]["visible"]
                    for t in self.tools):
                self.active_tabs[pane] = None

    def show_panel(self, panel_id: str, title: str, components: list, *, placement: str = "assistant",
                   owner: Any = None) -> dict:
        """Show (or replace) an agent-built panel made of ``hani2.tools.ui`` components.

        ``placement``: ``assistant`` (inside the assistant dock), ``side``
        (above the action panel) or ``modal``.
        """
        p = dict(id=str(panel_id), title=title, components=components, placement=placement)
        with self.lock:
            self.agent_panels = [x for x in self.agent_panels if x["id"] != p["id"]] + [p]
            if owner is not None:
                self._panel_owner = owner
        self.push_state()
        return {"ok": True, "panel": panel_id}

    def close_panel(self, panel_id: str | None = None) -> dict:
        with self.lock:
            self.agent_panels = [x for x in self.agent_panels if panel_id is not None and x["id"] != panel_id]
        self.push_state()
        return {"ok": True}

    def panel_event(self, panel_id: str, action: str, payload: dict) -> None:
        sa = self.support_agent
        if sa is not None:
            self.submit(sa.on_panel_action, panel_id, action, payload or {})

    # ------------------------------------------------------------------ #
    # Autopilot                                                           #
    # ------------------------------------------------------------------ #
    def set_autopilot(self, active: bool, driver: str | None = None) -> dict:
        from hani2.support_agent import autopilot as ap

        return ap.set_autopilot(self, active, driver)

    # ------------------------------------------------------------------ #
    # Snapshot sent to the browser                                        #
    # ------------------------------------------------------------------ #
    def _shown_text(self, text, data, by_human: bool) -> str | None:
        t = str(text) if text else (str(data.get("text")) if isinstance(data, dict) and data.get("text") else None)
        return t if by_human else self.relabel_text(t)

    def issues_spec(self) -> list[dict[str, Any]]:
        out = []
        info = (self.scenario.info or {}) if self.scenario is not None else {}
        role = str(self.ss.get("human_id", "")).replace(" (You)", "")
        descs = info.get("issue_description", {}) or {}
        for i in self.issues:
            kind = _issue_kind(i)
            d: dict[str, Any] = {"name": i.name, "kind": kind}
            if kind in ("int", "float"):
                d["min"], d["max"] = ui.jsonable(i.min_value), ui.jsonable(i.max_value)
                if kind == "int" and (i.max_value - i.min_value) <= 30:
                    d["values"] = list(range(int(i.min_value), int(i.max_value) + 1))
            else:
                d["values"] = ui.jsonable(list(i.all))
            if d.get("values"):
                from hani2.display import format_value, value_key
                from hani2.naming import relabel_value

                # the shown names: the scenario's value_labels / issue_format, then side words relabelled
                shown = {value_key(v): relabel_value(format_value(info, i.name, v), self.labels) if self.labels
                         else format_value(info, i.name, v) for v in d["values"]}
                if any(str(k) != str(v) for k, v in shown.items()):
                    d["labels"] = shown
            if (w := self.issue_widget(i.name)):
                d["widget"] = w
            desc = descs.get(role, {}).get(i.name) if isinstance(descs.get(role), dict) else descs.get(i.name)
            if desc:
                d["description"] = str(desc)
            out.append(d)
        return out

    @_in_own_study
    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            m = self.mechanism
            st = m.state if m is not None else None
            scenario = self.scenario
            info = (scenario.info or {}) if scenario is not None else {}
            partner = self.partner_offer()
            pdata = self.partner_data()
            draft_t = self.draft_outcome()
            show_partner = self.admin_mode or bool(self.admin_prefs.get("show_opponent_type"))
            tools = []
            for t in self.tools:
                if not self.tool_available(t):
                    continue
                s = self.tool_state(t)
                tools.append(
                    dict(id=s["id"], name=t.name, icon=t.icon, description=t.description, help=t.help_text(), pane=s["pane"],
                         order=s["order"], visible=s["visible"], enabled=s["enabled"], permanent=t.permanent,
                         added_by=s.get("added_by"))
                )
            sa = self.support_agent
            snap = {
                "sid": self.sid,
                "user": self.user,
                "display_name": self.display_name,
                "mode": self.mode,
                "is_admin": self.is_admin,
                "admin_mode": self.admin_mode,
                "participant_view": bool(self.admin_viewer),
                "phase": self.phase,
                "round": dict(number=self.round_number, practice=bool(self.ss.get("is_practice_round")),
                              label=self.study.round_label()),
                "scenario": None
                if scenario is None
                else dict(
                    name=self._scenario_name(),
                    type=(self.ss.get("scenario_info") or {}).get("scenario_type"),
                    title=info.get("title") or self._scenario_name(),
                    short_description=self.relabel_text(info.get("short_description", "")),
                    issues=self.issues_spec(),
                    n_issue_columns=int(info.get("n_issue_columns") or (3 if len(self.issues_spec()) >= 7 else 2)),
                    role="" if str(self.ss.get("human_id", "")).replace(" (You)", "").strip().lower() in self.labels
                    else str(self.ss.get("human_id", "")).replace(" (You)", ""),
                    opponent_role=self._opponent_role(),
                ),
                "opponent": dict(
                    name=short_name(self.ss.get("last_partner_type", "")),
                    type=str(self.ss.get("last_partner_type", "")),
                )
                if show_partner and self.ss.get("last_partner_type")
                else None,
                "negotiation": dict(
                    running=self.phase == "running",
                    thinking=self.thinking,
                    is_my_turn=self.is_my_turn(),
                    step=getattr(st, "step", 0),
                    n_steps=getattr(getattr(m, "nmi", None), "n_steps", None) if m else self.admin_prefs.get("n_steps"),
                    relative_time=getattr(st, "relative_time", 0.0) if st else 0.0,
                    deadline=self.deadline,
                    time_limit=getattr(getattr(m, "nmi", None), "time_limit", None) if m else self.admin_prefs.get("time_limit"),
                    server_time=time.time(),
                ),
                "partner_offer": None
                if partner is None
                else dict(values=self.outcome_to_dict(partner), text=self.relabel_text(self.outcome_str(partner)),
                          utility=self.shown_utility(partner, "human"), view=self.offer_view("table", partner),
                          message=(pdata or {}).get("text") if isinstance(pdata, dict) else None),
                "reserved_value": self.shown_reserved_value("human"),
                "information": self._information_client_state(),
                "draft": dict(values=dict(self.draft), text=self.draft_text,
                              utility=self.shown_utility(draft_t, "human")
                              if draft_t and all(v is not None for v in draft_t) else None,
                              controls=self.draft_controls()),
                "result": None if self.result is None else {
                    **self.result, "agreement_str": self.relabel_text(self.result.get("agreement_str"))},
                "history": self._shown_history(),  # a copy: the list grows while the state is sent
                "tools": tools,
                "active_tabs": dict(self.active_tabs),
                "reveal": getattr(self, "reveal", None),
                "prefs": dict(self.prefs),
                "settings": dict(self.admin_prefs)
                if self.is_admin
                else {k: self.admin_prefs.get(k) for k in (
                    "allow_text_human", "allow_text_agent", "allow_tool_switch", "allow_moving_tools",
                    "text_only_mode", "allow_scenario_selection")},
                "highlights": list(self.highlights),
                "annotations": dict(self.annotations),
                "layout": dict(self.layout),
                "agent_panels": list(self.agent_panels),
                "board": self.board,
                "pins": [dict(p) for p in self.pins],
                "notifications": [dict(n) for n in self.notifications[-100:]],
                "interface": self._interface_state(),
                "chat": list(self.chat),
                "pending_question": self.pending_question,
                "support": sa.client_state() if sa is not None else None,
                "autopilot": self._autopilot_state(),
                "notice": self.notice,
                "assistant_error": self.assistant_error,
                "model_error": self.__dict__.get("model_error"),
                "questionnaire": self.questionnaire,
                "finish_url": self.finish_url,
                "finish_text": self.finish_text,
                "project": self.study_ref.project if self.study_ref else projects.DEFAULT_PROJECT,
                "study_name": self.study_ref.study if self.study_ref else None,
                "study": self.study.client_state(),
                "can_choose_scenario": self.can_choose_scenario(),
                "webmcp": self.webmcp_policy(),
                "tool_maximize": self.tool_maximize_mode(),
                "next_opponent": self.next_opponent if self.admin_mode else None,
            }
        return snap

    def _interface_state(self) -> dict[str, Any]:
        """What the browser needs to show only what the participant may adjust."""
        pol = self.interface_policy()
        notes = pol.get("notifications") or {}
        try:
            secs = float(notes.get("toast_seconds", 6))
        except (TypeError, ValueError):
            secs = 6.0
        return {
            "participant_settings": {k: self.may_adjust(k, pol) for k in PARTICIPANT_SETTINGS},
            "hidden_from_participants": [k for k, v in pol["participant_settings"].items() if not v],
            "toast_ms": int(max(0.0, secs) * 1000),
            "notification_center": bool(notes.get("center", True)),
            "assistant": self.assistant_presentation(),
            "move_tools": bool(self.admin_prefs.get("allow_moving_tools", True)),
        }

    def tool_maximize_mode(self) -> str:
        """How an enlarged tool opens: ``window`` (a large dialog), ``fullscreen``
        or ``off`` (no enlarge button); env.json → ``tools.maximize``."""
        mode = str(get_env("tools.maximize", "window") or "window").lower()
        return mode if mode in ("window", "fullscreen", "off") else "window"

    def webmcp_policy(self) -> dict[str, bool]:
        """Whether the page exposes WebMCP tools, and whether they may act.

        Configured in env.json → ``webmcp``: ``enabled`` (default true),
        ``actions`` (default true; false = read-only tools) and ``studies``
        (default false: Prolific participants get no WebMCP tools, so a
        browser agent cannot play their study for them)."""
        cfg = get_env("webmcp", {}) or {}
        enabled = bool(cfg.get("enabled", True))
        if self.user.startswith("prolific_") and not cfg.get("studies", False):
            enabled = False
        return {"enabled": enabled, "actions": enabled and bool(cfg.get("actions", True))}

    def _autopilot_state(self) -> dict[str, Any]:
        try:
            from hani2.support_agent import autopilot as ap

            return ap.client_state(self)
        except Exception:
            traceback.print_exc()
            return {"available": False}

    def submit_ui(self, fn: Callable, *args, **kwargs):
        """Run a UI message handler in order with the other UI messages."""

        def _run():
            try:
                with rec.bind(self.sid), projects.use_study(self.study_ref):
                    return fn(*args, **kwargs)
            except Exception:  # noqa: BLE001
                traceback.print_exc()

        return self.ui_executor.submit(_run)

    @_in_own_study
    def close(self) -> None:
        self.closed = True
        self.study.close()
        if self.recorder is not None:
            self.recorder.close()
        self.ui_executor.shutdown(wait=False, cancel_futures=True)
        if self._timer is not None:
            self._timer.cancel()
        ev.end_session_record(self.sid)
        projects.forget_session(self.sid)


#: Element names the Assistant (or tool) can highlight / annotate.
ANCHORS = {
    "accept": "The Accept button",
    "reject": "The Reject / counter-offer button",
    "end": "The End negotiation button",
    "send": "The Send counter-offer button",
    "offer": "The counter-offer editor",
    "message": "The message box",
    "partner_offer": "The opponent's current offer",
    "history": "The negotiation history",
    "timer": "The countdown / progress area",
    "issue:<name>": "One issue field in the counter-offer editor",
    "history:last": "The latest history entry",
    "tool:<name>": "A tool tab",
    "pane:upper|lower|side": "A tool pane",
}
