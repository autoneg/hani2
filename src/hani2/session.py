"""The negotiation session engine.

One :class:`NegotiationSession` exists per browser session (a cookie, or a
Prolific PID). It owns the scenario, the negmas mechanism, the human's draft
offer, the history, the tools, the support agent and the autopilot, and pushes
state to every connected browser tab through :class:`hani2.hub.Hub`.

Threading model
---------------
* Every public method may be called from any thread.
* ``self.lock`` (re-entrant) guards session state; hold it only briefly.
* ``self.step_lock`` serialises mechanism stepping. Partner steps (which may
  call slow LLMs) run in a worker thread and never hold ``self.lock``, so the
  UI, tools and the support agent stay responsive while the partner thinks.
* :meth:`run_on_doc` runs a callable under ``self.lock`` — it is what support
  agents use to read or change UI-owned state safely.
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
}

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

#: Set while the support agent operates a tool (see ``acting_for_agent``).
_AGENT_CONTEXT = threading.local()

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


class NegotiationSession:
    def __init__(
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
    ):
        self.sid = sid
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
        self.highlights: list[dict[str, Any]] = []
        self.annotations: dict[str, dict[str, Any]] = {}
        self.agent_panels: list[dict[str, Any]] = []
        self.layout: dict[str, Any] = {"view": self.query.get("view") or "full", "sizes": {}}
        self.pending_question: dict[str, Any] | None = None
        self.notice: dict[str, Any] | None = None
        self.questionnaire: dict[str, Any] | None = None
        self.finish_url: str | None = None
        self.draft: dict[str, Any] = {}
        self.draft_text: str = ""
        self.thinking = False
        self.deadline: float | None = None
        self.result: dict[str, Any] | None = None
        self.human_action: SAOResponse = SAOResponse(ResponseType.REJECT_OFFER, None)
        self.human_last_offer: Outcome | None = None
        self._trace_seen = 0
        self._timer: threading.Timer | None = None
        self.autopilot_active = False
        self.autopilot_driver_name: str | None = None
        self.next_opponent: str = ""

        user_path = results_root() / user
        user_path.mkdir(parents=True, exist_ok=True)
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

        self.support_agent = create_support_agent_for(self)
        ev.start_session_record(sid, user, mode, user_agent=user_agent)
        ev.log_event(sid, ev.EventType.SESSION_START, user=user, value={"mode": mode})

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

    def submit(self, fn: Callable, *args, **kwargs):
        actor = rec.current_actor()

        def _run():
            try:
                with rec.bind(self.sid), rec.acting(actor) if actor else contextlib.nullcontext():
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

    def toast(self, message: str, level: str = "info", duration: int | None = None, action: dict | None = None) -> bool:
        self.emit({"type": "toast", "message": str(message), "level": level, "duration": duration, "action": action})
        return True

    def utility(self, outcome) -> float | None:
        if outcome is None or self.human_ufun is None:
            return None
        try:
            return float(self.human_ufun(tuple(outcome)))
        except Exception:
            return None

    @property
    def labels(self) -> dict[str, str]:
        """Display names for side words (``{"human": "You", "agent": "Partner"}``)
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

    def outcome_str(self, outcome, from_human: bool = False, done: bool = False) -> str:
        disp = self.ss.get("outcome_display")
        if disp is None or self.scenario is None:
            return str(outcome)
        try:
            return disp.str(outcome, self.scenario, done, from_human)
        except Exception:
            return str(outcome)

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
                pane = spec.pane
                order = spec.order + (0 if spec.at_front else 1000)
                self.tools.append(tool)
                self._tool_states[id(tool)] = dict(
                    id=uuid.uuid4().hex[:10],
                    pane=pane,
                    order=order,
                    visible=True,
                    enabled=bool(tool.enabled),
                )
                try:
                    tool.init(self.ss)
                except Exception:
                    traceback.print_exc()
                if spec.at_front or self.active_tabs.get(pane) is None:
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
            visible = [t for t in self.tools if self._tool_states[id(t)]["visible"]]
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

    def render_tool(self, tid: str) -> dict[str, Any] | None:
        t = self.tool_by_id(tid)
        if t is None:
            return None
        st = self.tool_state(t)
        if not st["enabled"] and not t.permanent and self.admin_prefs.get("allow_tool_switch", True):
            return {"id": tid, "view": None}
        return {"id": tid, "view": self.relabel(t.render())}

    def tool_input(self, tid: str, name: str, value: Any) -> None:
        t = self.tool_by_id(tid)
        if t is None:
            return
        try:
            t.on_input(name, value)
        except Exception:
            traceback.print_exc()
        ev.log_event(self.sid, ev.EventType.TOOL_INTERACTION, user=self.user, component=t.name, action=f"input:{name}")

    def tool_action(self, tid: str, action: str, payload: dict[str, Any]) -> None:
        t = self.tool_by_id(tid)
        if t is None:
            return
        try:
            t.on_action(action, payload or {})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.toast(f"{t.name}: {e}", "error")
        ev.log_event(self.sid, ev.EventType.TOOL_INTERACTION, user=self.user, component=t.name, action=action)

    # ------------------------------------------------------------------ #
    # Preferences                                                         #
    # ------------------------------------------------------------------ #
    def set_pref(self, key: str, value: Any) -> bool:
        key = PREF_ALIASES.get(key, key)
        with self.lock:
            if key in USER_PREFS:
                self.prefs[key] = value
            elif key in ADMIN_PREFS and self.is_admin:
                self.admin_prefs[key] = value
            else:
                return False
        self.push_state()
        return True

    # ------------------------------------------------------------------ #
    # Scenario loading                                                    #
    # ------------------------------------------------------------------ #
    def load(self, scenario_type: str | None = None, name: str | None = None) -> None:
        """Load the next scenario (no negotiation is started)."""
        with self.lock:
            if self.phase in ("running", "starting", "questionnaire"):
                return
            if self.study.finished():
                self.phase = "finished"
                self.finish_url = self.study.completion_url()
                self.push_state()
                return
            plan = self.study.plan_round(scenario_type if self.can_choose_scenario() else None, name)
            idx = plan.get("index")
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
                )
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self.toast(f"Could not load a scenario: {e}", "error")
                return
            self.round_plan = plan
            self.ss["is_practice_round"] = bool(plan.get("practice", False))
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
            self.phase = "ready"
        if self.recorder is not None:
            self.recorder.begin()
            self.recorder.scenario()
        self._add_tools("load")
        self._tools_hook("scenario_loaded", scenario)
        ev.log_event(self.sid, ev.EventType.SCENARIO_LOADED, user=self.user, scenario_id=str(info.get("scenario_name")))
        self.push_state()
        self.study.after_load()

    def can_choose_scenario(self) -> bool:
        return self.is_admin or bool(self.admin_prefs.get("allow_scenario_selection", False))

    # ------------------------------------------------------------------ #
    # Opponents                                                           #
    # ------------------------------------------------------------------ #
    def opponent_pool(self) -> list:
        """The opponents this session may face, first match wins: the page's
        ``?opponents=`` / ``?group=``, ``hani2 --opponents`` (``HANI2_OPPONENTS``),
        the admin session setting ``opponent_types``, ``opponents`` in env.json,
        else the built-in default pool. Old names (``?agents=``,
        ``HANI2_AGENTS``, ``agents``) are still read."""
        override = session_agent_override(self.query)
        if override:
            return override
        cmdline = (os.environ.get("HANI2_OPPONENTS") or os.environ.get("HANI2_AGENTS") or "").strip()
        if cmdline:
            pool = expand_agents(cmdline)
            if pool:
                return pool
        pool = expand_agents(self.admin_prefs.get("opponent_types") or [])
        if pool:
            return pool
        pool = expand_agents(get_env("opponents", []) or get_env("agents", []) or [])
        return pool or list(DEFAULT_POOL)

    partner_pool = opponent_pool  # old name

    def choose_partner(self) -> str:
        plan = getattr(self, "round_plan", {}) or {}
        if plan.get("partner"):
            return plan["partner"]
        if self.admin_mode and self.next_opponent:
            return self.next_opponent
        return random.choice(self.opponent_pool())

    # ------------------------------------------------------------------ #
    # Starting a negotiation                                              #
    # ------------------------------------------------------------------ #
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
        self._tools_hook("negotiation_started")
        ev.log_event(self.sid, ev.EventType.SCENARIO_STARTED, user=self.user, scenario_id=self._scenario_name(),
                     value={"partner": self.ss.get("last_partner_type")})
        self._schedule_timeout()
        self._agent_event("negotiation_started")
        self.push_state()
        self._step_to_human(wait=30.0)  # a step of the previous round may still be finishing

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
                self.layout["view"] = "full"
                self.ss["view_mode"] = "full"
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
            self.emit({"type": "history", "items": self.history})

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

    def act(self, response: SAOResponse) -> bool:
        """Queue the human's response and advance in the background."""
        with self.lock:
            if not self.is_my_turn() or self.thinking:
                return False
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
        """Step the partner until it is the human's turn. ``wait`` seconds to
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
        elif self.admin_prefs.get("init_with_best", True) and self.human_ufun is not None:
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
        except (TypeError, ValueError):
            return value
        return value

    def set_draft(self, values: dict[str, Any], *, by_agent: bool = False) -> dict:
        if (refused := self._agent_gate("fill_offer")) is not None:
            return refused
        applied, missing = {}, []
        with self.lock:
            for key, value in (values or {}).items():
                issue = self._resolve_issue(key)
                if issue is None:
                    missing.append(key)
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
        self.emit({"type": "draft", "draft": self.draft, "utility": util, "by_agent": by_agent})
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
        return {"ok": not missing, "applied": applied, "unrecognised": missing}

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

    def accept(self) -> bool:
        if self._agent_gate("accept") is not None:
            return False
        offer = self.partner_offer()
        if offer is None:
            return False
        ev.log_event(self.sid, ev.EventType.OFFER_ACCEPTED, user=self.user, scenario_id=self._scenario_name(),
                     utility_value=self.utility(offer), round_number=self.mechanism.state.step if self.mechanism else None)
        return self.act(SAOResponse(ResponseType.ACCEPT_OFFER, offer))

    def end(self) -> bool:
        if self._agent_gate("end") is not None:
            return False
        with self.lock:
            self.ss["human_ended_negotiation"] = True
        ev.log_event(self.sid, ev.EventType.NEGOTIATION_ENDED, user=self.user, action="end_by_human")
        return self.act(SAOResponse(ResponseType.END_NEGOTIATION, None))

    def send_counter(self, text: str | None = None, offer: dict | None = None, text_only: bool | None = None) -> dict:
        """Send the counter-offer (the draft offer plus the message)."""
        if (refused := self._agent_gate("submit_counter")) is not None:
            return refused
        if offer:
            self.set_draft(offer)
        if text is not None:
            self.set_draft_text(text)
        p = self.admin_prefs
        text_only = bool(p.get("text_only_mode")) if text_only is None else (bool(text_only) and self.is_admin)
        msg = (self.draft_text or "").strip() if p.get("allow_text_human", True) else ""
        if p.get("auto_extract") and not text_only and msg:
            try:
                self.extract_offer_from_text()
            except Exception:
                traceback.print_exc()
        if p.get("auto_generate") and not text_only and not msg:
            msg = self._llm_generate_text() or ""
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
        with self.lock:
            self.human_last_offer = outcome if outcome is not None else self.human_last_offer
            self.draft_text = ""
        ev.log_event(self.sid, ev.EventType.COUNTER_OFFER, user=self.user, scenario_id=self._scenario_name(),
                     value={"offer": self.outcome_to_dict(outcome), "text": msg}, utility_value=self.utility(outcome))
        ok = self.act(SAOResponse(ResponseType.REJECT_OFFER, outcome, data))
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
            {"role": "You" if h["by"] == "human" else "Partner", "text": h.get("text") or "", "outcome": str(h.get("offer") or "")}
            for h in self.history[-10:]
        ]
        return NegotiationContext(
            issues=self.issues,
            outcome_space=self.scenario.outcome_space if self.scenario else None,
            ufun=self.human_ufun,
            history=hist or None,
            current_offer=self.partner_offer(),
        )

    def extract_offer_from_text(self) -> dict:
        from hani2.llm_service import extract_outcome_from_text

        res = extract_outcome_from_text(self.draft_text or "", self.issues, context=self.llm_context())
        if res.error:
            return {"ok": False, "error": res.error}
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
        if self.deadline is None:
            return
        delay = max(0.0, self.deadline - time.time()) + 0.25
        self._timer = threading.Timer(delay, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()

    def _on_timeout(self) -> None:
        if self.phase != "running":
            return
        if self.autopilot_active:
            self._schedule_timeout()
            return
        if self.is_my_turn() and not self.thinking:
            self.toast("Time's up!", "warning")
            self.act(SAOResponse(ResponseType.REJECT_OFFER, self.human_last_offer))
        else:
            # the partner's own step will notice the timeout; check again shortly
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
                msg = "Your partner ended the negotiation without agreement."
            else:
                msg = "The negotiation ended without agreement."
            self.history.append(dict(id=len(self.history), kind="system", text=msg, status=summary.get("status"), time=time.time()))
            # the study's end-of-round step (notice, questionnaire, finish link) happens
            # before anyone can see or act on the ended round
            try:
                self.study.after_round(summary)
            finally:
                self._finishing = False
            self.emit({"type": "history", "items": self.history})
        self._add_tools("end")
        self._tools_hook("negotiation_ended")
        ev.log_event(self.sid, ev.EventType.NEGOTIATION_ENDED, user=self.user, scenario_id=self._scenario_name(),
                     value={k: ui.jsonable(v) for k, v in summary.items()}, utility_value=summary.get("human_utility"))
        self._agent_event("negotiation_ended")
        self.push_state()

    # ------------------------------------------------------------------ #
    # Support agent bridge                                                #
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
        """Remember queued support-agent work so tests can wait for it."""
        with self.lock:
            pending = self.__dict__.setdefault("_agent_futures", set())
            pending.add(future)
        future.add_done_callback(lambda f: self.__dict__.get("_agent_futures", set()).discard(f))

    def agent_work_pending(self) -> bool:
        return any(not f.done() for f in list(self.__dict__.get("_agent_futures", ())))

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
    # The action API shared by the UI and the support agent                #
    # ------------------------------------------------------------------ #
    def context(self) -> dict[str, Any]:
        m = self.mechanism
        st = m.state if m is not None else None
        partner = self.partner_offer()
        draft_t = self.draft_outcome()

        def _issue_info(i):
            info: dict[str, Any] = {"name": i.name}
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
                "utility": h.get("utility"),
            }
            for h in self.history[-14:]
            if h.get("kind") == "offer"
        ]
        return {
            "issues": [_issue_info(i) for i in self.issues],
            "partner_offer": self.display_outcome(self.outcome_to_dict(partner)),
            "partner_offer_utility": self.utility(partner),
            "partner_message": self.relabel_text((self.partner_data() or {}).get("text"))
            if isinstance(self.partner_data(), dict) else None,
            "draft_offer": self.display_outcome(dict(self.draft)),
            "draft_offer_utility": self.utility(draft_t) if draft_t and all(v is not None for v in draft_t) else None,
            "draft_message": self.draft_text,
            "reserved_value": self.reserved_value(),
            "is_my_turn": self.is_my_turn(),
            "phase": self.phase,
            "step": getattr(st, "step", None),
            "n_steps": getattr(getattr(m, "nmi", None), "n_steps", None),
            "relative_time": getattr(st, "relative_time", None),
            "time_left": max(0.0, self.deadline - time.time()) if self.deadline else None,
            "history": history,
            "result": self.result,
            "tools": [t.name for t in self.tools],
            **({"names": "Values are shown with these names: "
                         + ", ".join(f"{v} = {'the participant' if k == 'human' else 'the opponent (partner)'}"
                                     for k, v in self.labels.items())
                         + ". Use these names with the participant and in offers. The message to the partner is "
                           "read by the partner, so there say who gets what in plain words (for example "
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
        (a browser message), ``agent`` (the support agent or a tool working for
        it) or ``autopilot``."""
        if getattr(_AGENT_CONTEXT, "caps", None) is not None:
            return "agent"
        return rec.current_actor() or "human"

    def _agent_gate(self, capability: str) -> dict | None:
        """While the support agent operates a tool (:meth:`acting_for_agent`),
        refuse what the agent itself may not do; ``None`` means allowed."""
        caps = getattr(_AGENT_CONTEXT, "caps", None)
        if caps is None or capability in caps:
            return None
        return {"ok": False, "error": f"the support agent is not allowed to do this ({capability} is off)"}

    @contextlib.contextmanager
    def acting_for_agent(self, capabilities: set[str]):
        """Run tool callbacks on behalf of the support agent: actions the tool
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
                    self.layout[k] = v
            self.ss["view_mode"] = self.layout.get("view")
        self.push_state()
        return {"ok": True, "layout": dict(self.layout)}

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
                if self.labels:
                    from hani2.naming import relabel_value

                    shown = {str(v): relabel_value(v, self.labels) for v in d["values"]}
                    if any(str(k) != str(v) for k, v in shown.items()):
                        d["labels"] = shown
            desc = descs.get(role, {}).get(i.name) if isinstance(descs.get(role), dict) else descs.get(i.name)
            if desc:
                d["description"] = str(desc)
            out.append(d)
        return out

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
                          utility=self.utility(partner),
                          message=(pdata or {}).get("text") if isinstance(pdata, dict) else None),
                "reserved_value": self.reserved_value(),
                "draft": dict(values=dict(self.draft), text=self.draft_text,
                              utility=self.utility(draft_t) if draft_t and all(v is not None for v in draft_t) else None),
                "result": None if self.result is None else {
                    **self.result, "agreement_str": self.relabel_text(self.result.get("agreement_str"))},
                "history": self.history,
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
                "chat": list(self.chat),
                "pending_question": self.pending_question,
                "support": sa.client_state() if sa is not None else None,
                "autopilot": self._autopilot_state(),
                "notice": self.notice,
                "questionnaire": self.questionnaire,
                "finish_url": self.finish_url,
                "study": self.study.client_state(),
                "can_choose_scenario": self.can_choose_scenario(),
                "webmcp": self.webmcp_policy(),
                "tool_maximize": self.tool_maximize_mode(),
                "next_opponent": self.next_opponent if self.admin_mode else None,
            }
        return snap

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
                with rec.bind(self.sid):
                    return fn(*args, **kwargs)
            except Exception:  # noqa: BLE001
                traceback.print_exc()

        return self.ui_executor.submit(_run)

    def close(self) -> None:
        if self.recorder is not None:
            self.recorder.close()
        self.ui_executor.shutdown(wait=False, cancel_futures=True)
        if self._timer is not None:
            self._timer.cancel()
        ev.end_session_record(self.sid)


#: Element names a support agent (or tool) can highlight / annotate.
ANCHORS = {
    "accept": "The Accept button",
    "reject": "The Reject / counter-offer button",
    "end": "The End negotiation button",
    "send": "The Send counter-offer button",
    "offer": "The counter-offer editor",
    "message": "The message box",
    "partner_offer": "The partner's current offer",
    "history": "The negotiation history",
    "timer": "The countdown / progress area",
    "issue:<name>": "One issue field in the counter-offer editor",
    "history:last": "The latest history entry",
    "tool:<name>": "A tool tab",
    "pane:upper|lower|side": "A tool pane",
}
