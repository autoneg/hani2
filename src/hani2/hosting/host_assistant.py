"""Run an unchanged HANI2 Assistant class on a team's host (``hani2 host-assistant module:Class``).

The class is subclassed on the fly so that

* its helpers that change the participant's screen (``post``, ``toast``, ``show_on_board``,
  ``highlight``, ``set_layout``, …) become **actions** sent back to HANI2 with the reply;
* the functions its language model calls (``get_negotiation_state``, ``set_offer``,
  ``submit_counter_offer``, ``use_tool``, …) become **calls**: the turn pauses, HANI2 runs the function
  in the real session (capabilities and autonomy apply there) and sends the result back;
* functions its own dispatcher adds (``register_extra_tools``) run here on the host;
* ``session_state["actions"]`` (``context``, ``set_offer``, ``accept``, …) maps to the same functions;
* its language model is the host's own (the host's HANI2 model chain or its own ``_complete``).

What does not work on a host: reading interface objects directly (``self.session.<anything else>``
raises a clear error), and speaking outside a turn (a host answers events; it cannot push).
"""

from __future__ import annotations

import inspect
import queue
import threading
import traceback
import uuid
from types import SimpleNamespace
from typing import Any

from hani2.hosting.protocol import HostedError, check_outcome, decode_outcome_space, issue_names, json_safe, model_label

#: Assistant helpers that become actions (when the class does not override them)
ACTION_HELPERS = ("post", "toast", "show_on_board", "message_user", "pin_message", "unpin_message", "highlight",
                  "clear_highlights", "annotate", "set_layout", "set_offer_display", "set_interface",
                  "set_presentation", "set_opponent_estimate", "focus_tool", "show_panel", "close_panel")
#: how long a paused turn waits for HANI2's results (a function may ask the participant a question)
RESULTS_WAIT = 300.0
#: how long one HTTP step waits for the agent's next calls or its end
STEP_WAIT = 290.0


def assistant_factory(spec: Any) -> type:
    from hani2.support_agent.runtime import SupportAgent, load_assistant_class

    if isinstance(spec, type):
        if not issubclass(spec, SupportAgent):
            raise TypeError(f"{spec!r} is not an Assistant (SupportAgent) subclass")
        return spec
    return load_assistant_class(str(spec))


class ProxySession:
    """What a hosted Assistant sees as ``self.session``: the latest context from HANI2, actions for what
    changes the screen, calls for what needs the real session."""

    def __init__(self, runner: "AssistantRunner", outcome_space: Any):
        self._r = runner
        self.lock = threading.RLock()
        self.is_admin = False
        self.sid = "hosted"
        self.user = "remote"
        self.models = None
        self.recorder = None
        self.information = None
        self.pending_question = None
        self.board = ""
        self.prefs: dict[str, Any] = {}
        self.outcome_space = outcome_space
        self.scenario = SimpleNamespace(outcome_space=outcome_space) if outcome_space is not None else None

    @property
    def issues(self) -> list:
        return list(getattr(self.outcome_space, "issues", ()) or ())

    def context(self, view: str | None = None) -> dict:
        return self._r.context()

    def opponent_context(self) -> dict:
        return dict((self._r.context() or {}).get("opponent") or {})

    def run_on_doc(self, fn, timeout: float = 30.0):
        return fn()

    def submit(self, fn, *a, **kw):
        return fn(*a, **kw)

    def push_state(self) -> None:
        pass

    def emit(self, msg: dict) -> None:
        pass

    def is_my_turn(self) -> bool:
        return bool((self._r.context() or {}).get("is_my_turn"))

    def add_chat(self, user: str, text: str, kind: str | None = None, extra: dict | None = None) -> None:
        self._r.action("post", text=str(text))

    def toast(self, message: str, level: str = "info", duration: int | None = None, action: dict | None = None,
              source: str = "assistant") -> bool:
        self._r.action("toast", message=str(message), level=level)
        return True

    def annotate(self, target: str, text: str | None, kind: str = "info") -> dict:
        self._r.action("annotate", target=target, text=text, kind=kind)
        return {"ok": True}

    def send_counter(self, text: str | None = None) -> dict:
        return self._r.call("submit_counter_offer", {"message": text} if text else {})

    def accept(self) -> dict:
        return self._r.call("accept_offer", {})

    def end(self) -> dict:
        return self._r.call("end_negotiation", {})

    def set_autopilot(self, on: bool) -> None:
        self._r.action("set_autopilot", active=bool(on))

    def offer_outcome(self, offer: dict) -> tuple | None:
        try:
            return check_outcome(offer, self.outcome_space)
        except HostedError:
            return None

    def outcome_to_dict(self, outcome: Any) -> dict:
        return dict(zip(issue_names(self.outcome_space), outcome)) if outcome is not None else {}

    def display_outcome(self, d: Any) -> Any:
        return d

    def llm_context(self, audience: str = "assistant"):
        """What the default message / offer prompts know here: the issues, the recent offers and the
        offer on the table from HANI2's context (the utility function stays with HANI2)."""
        from hani2.llm_service import NegotiationContext

        ctx = self._r.context() or {}
        hist = []
        for h in list(ctx.get("history") or [])[-10:]:
            if isinstance(h, dict):
                hist.append({"role": "You" if h.get("by") in ("human", "you") else "Opponent",
                             "text": str(h.get("text") or ""), "outcome": str(h.get("offer") or "")})
        po = ctx.get("partner_offer")
        return NegotiationContext(issues=self.issues, outcome_space=self.outcome_space, ufun=None, history=hist or None,
                                  current_offer=self.offer_outcome(po) if isinstance(po, dict) else None)

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(f"a hosted Assistant cannot use session.{name} on its host; use the Assistant "
                             "helpers (post, toast, highlight, …) or its functions (get_negotiation_state, …)")


def _emitter(name: str, base_fn: Any):
    sig = inspect.signature(base_fn)

    def f(self, *a: Any, **kw: Any) -> Any:
        ba = sig.bind(self, *a, **kw)
        args = {k: v for k, v in ba.arguments.items() if k != "self"}
        for p in sig.parameters.values():  # set_layout(**changes) and the like: flatten
            if p.kind == inspect.Parameter.VAR_KEYWORD and p.name in args:
                args.update(args.pop(p.name) or {})
        self._hosted_runner.action(name, **args)
        return True if name in ("toast", "show_on_board") else ({"ok": True} if name not in ("post", "message_user")
                                                                  else None)

    f.__name__ = name
    return f


def _hosted_class(klass: type) -> type:
    """``klass`` with its screen helpers turned into actions and its functions into calls."""
    from hani2.support_agent.runtime import SupportAgent
    from hani2.support_agent.tools import ToolDispatcher

    def base(n: str) -> bool:  # the class does not override this helper itself
        return getattr(klass, n, None) is getattr(SupportAgent, n, None)

    attrs: dict[str, Any] = {n: _emitter(n, getattr(SupportAgent, n)) for n in ACTION_HELPERS if base(n)}

    def ask_user(self, question: str, options: list[str] | None = None, timeout: float = 180.0) -> str | None:
        r = self._hosted_runner.call("ask_user", {"question": question, "options": list(options or [])})
        return r.get("answer") if isinstance(r, dict) and r.get("ok") else None

    def opponent_view(self, offer: dict | None = None) -> dict:
        return self._hosted_runner.call("get_opponent_utility", {"offer": offer} if offer is not None else {})

    def private_information(self) -> dict:
        return self._hosted_runner.call("get_private_information", {})

    def past_negotiation(self, pid: str) -> dict:
        return self._hosted_runner.call("show_past_negotiation", {"id": pid})

    def read_tool(self, name: str, max_chars: int = 4000) -> dict:
        return self._hosted_runner.call("read_tool", {"name": name})

    def available_tools(self) -> list:
        r = self._hosted_runner.call("list_tools", {})
        return r.get("can_add") or [] if isinstance(r, dict) else []

    def add_tool(self, tool: Any, *, pane: str | None = None, at_front: bool = True, focus: bool = True) -> dict:
        name = tool if isinstance(tool, str) else getattr(tool, "name", None) or getattr(tool, "__name__", str(tool))
        return self._hosted_runner.call("add_tool", {"name": name, **({"pane": pane} if pane else {}), "focus": focus})

    def remove_tool(self, name: str) -> dict:
        return self._hosted_runner.call("remove_tool", {"name": name})

    def use_tool(self, name: str, *, inputs: dict | None = None, action: str | None = None, row: int | None = None,
                 payload: dict | None = None, **_: Any) -> dict:
        args: dict[str, Any] = {"name": name}
        for k, v in (("inputs", inputs), ("action", action), ("row", row), ("payload", payload)):
            if v is not None:
                args[k] = v
        return self._hosted_runner.call("use_tool", args)

    def context(self) -> dict:
        return self._hosted_runner.context()

    def run_on_doc(self, fn, timeout: float = 30.0):
        return fn()

    def _post_async(self, fn) -> None:
        fn()

    def _set_busy_state(self) -> None:
        pass

    def on_draft_changed(self, draft: dict) -> None:  # HANI2 shows the reserved-value warning itself
        pass

    for n, fn in (("ask_user", ask_user), ("opponent_view", opponent_view), ("private_information", private_information),
                  ("past_negotiation", past_negotiation), ("read_tool", read_tool),
                  ("available_tools", available_tools), ("add_tool", add_tool), ("remove_tool", remove_tool),
                  ("use_tool", use_tool), ("context", context), ("run_on_doc", run_on_doc),
                  ("_post_async", _post_async), ("on_draft_changed", on_draft_changed)):
        if base(n):
            attrs[n] = fn
    attrs["_set_busy_state"] = _set_busy_state

    dk = klass.dispatcher_class

    class HostedDispatcher(dk):  # type: ignore[valid-type,misc]
        def __init__(self, runtime: Any):
            super().__init__(runtime)
            probe = ToolDispatcher(runtime)
            #: functions this class adds itself: they run on the host
            self.local_names = set(self._registry) - set(probe._registry)

        def schemas(self) -> list[dict]:
            remote = list(self.runtime._hosted_runner.functions)
            names = {(s.get("function") or {}).get("name") for s in remote}
            for n in self.local_names:
                cap, _, schema = self._registry[n]
                if (cap is None or self.caps.has(cap)) and n not in names:
                    remote.append(schema())
            return remote

        def execute(self, name: str, args: dict) -> dict:
            if name in self.local_names:
                return super().execute(name, args)
            return self.runtime._hosted_runner.call(name, args or {})

    attrs["dispatcher_class"] = HostedDispatcher
    attrs["__module__"] = klass.__module__
    return type(f"Hosted{klass.__name__}", (klass,), attrs)


class AssistantRunner:
    """One hosted Assistant for one negotiation: its own instance, conversation and state."""

    def __init__(self, klass: type, setup: dict, model: Any = None):
        from hani2.support_agent.settings import load_support_agent_settings

        self._klass = klass
        os_ = decode_outcome_space(setup["outcome_space"]) if setup.get("outcome_space") else None
        self.functions: list[dict] = list(setup.get("functions") or [])
        self._ctx: dict | None = None
        self._actions: list[dict] = []
        self._outbox: queue.Queue = queue.Queue()
        self._inbox: queue.Queue = queue.Queue()
        self._turn_thread: threading.Thread | None = None
        # a turn is open from its event until its reply is posted; the turn's thread may still be exiting
        # when HANI2 (which has the reply) sends the next event, so that thread being alive is not enough
        # (and a thread that died without a reply does not keep the turn open)
        self._turn_open = False
        self._pending: str | None = None
        self.session = ProxySession(self, os_)
        try:
            settings = dict(load_support_agent_settings() or {})
        except Exception:  # noqa: BLE001
            settings = {}
        hs = setup.get("settings") or {}
        if hs.get("proactive") is not None:
            settings["proactive"] = hs["proactive"]
        if hs.get("max_tool_iterations"):
            settings["max_tool_iterations"] = hs["max_tool_iterations"]
        settings["capabilities"] = {c: True for c in setup.get("capabilities") or []}
        settings["autonomy"] = setup.get("autonomy") or "suggest"
        ss = {"_session": self.session, "user": "remote", "support_agent_default_enabled": True,
              "support_agent_user_enabled": bool(setup.get("user_enabled", True)),
              "support_proactive_delivery": setup.get("proactive_delivery") or "toast",
              "actions": self._actions_dict()}
        hosted = _hosted_class(klass)
        hosted._hosted_runner = self  # the class is per runner, so this never leaks between sessions
        self.agent = hosted(ss, settings)
        self._explicit_model = model
        self._model: Any = None

    # -- what the agent sees -----------------------------------------------------
    def context(self) -> dict:
        if self._ctx is None and self._turn_thread is threading.current_thread():
            r = self.call("get_negotiation_state", {})
            if isinstance(r, dict) and r.get("ok", True):
                self._ctx = {k: v for k, v in r.items() if k != "ok"}
        return dict(self._ctx or {})

    def _actions_dict(self) -> dict:
        return {
            "context": self.context,
            "set_offer": lambda outcome: self.call("set_offer", {"outcome": outcome}),
            "set_text": lambda text: self.call("set_message_text", {"text": text}),
            "get_offer": lambda: dict((self.context() or {}).get("draft_offer") or {}),
            "get_partner_offer": lambda: (self.context() or {}).get("partner_offer"),
            "can_act": lambda: bool((self.context() or {}).get("is_my_turn")),
            "highlight": lambda target, message=None, **kw: self.action("highlight", target=target, message=message, **kw),
            "accept": lambda confirm=True: self.call("accept_offer", {}),
            "end": lambda confirm=True: self.call("end_negotiation", {}),
            "reject_counter": lambda: self.call("submit_counter_offer", {}),
        }

    def model_info(self) -> Any:
        if self._explicit_model:
            return self._explicit_model
        if self._model is None:
            try:
                res = self.agent.model()
                self._model = {"provider": getattr(res, "provider", "") or "", "model": getattr(res, "model", "") or ""} \
                    if res is not None and getattr(res, "ok", False) else ""
            except Exception:  # noqa: BLE001
                self._model = ""
        return self._model or None

    # -- the agent's side of a turn --------------------------------------------------
    def action(self, name: str, **args: Any) -> None:
        self._actions.append({"action": name, "arguments": json_safe(args)})

    def _flush(self) -> list[dict]:
        out, self._actions = self._actions, []
        return out

    def call(self, name: str, args: dict) -> Any:
        """A function HANI2 runs in the real session; blocks this turn until its result comes back."""
        if self._turn_thread is not threading.current_thread():
            raise HostedError(f"{name}: a hosted Assistant can only call functions while it handles an event")
        cid = uuid.uuid4().hex[:10]
        self._pending = cid
        self._outbox.put({"status": "calls", "actions": self._flush(),
                          "calls": [{"id": cid, "function": name, "arguments": json_safe(args or {})}]})
        try:
            results = self._inbox.get(timeout=RESULTS_WAIT)
        except queue.Empty:
            raise HostedError(f"{name}: HANI2 sent no result") from None
        finally:
            self._pending = None
        self._ctx = None  # the session may have changed: read it afresh when next needed
        if isinstance(results, dict) and results.get("__abort__"):
            raise HostedError("the turn was abandoned")
        for r in results if isinstance(results, list) else []:
            if isinstance(r, dict) and r.get("id") == cid:
                return r.get("result")
        return {"ok": False, "error": "no result"}

    # -- HANI2's side ------------------------------------------------------------------
    def _sync(self, body: dict) -> None:
        from hani2.support_agent.capabilities import CapabilityState

        if body.get("functions") is not None:
            self.functions = list(body["functions"])
        if body.get("context") is not None:
            self._ctx = dict(body["context"])
        a = self.agent
        if body.get("capabilities") is not None:
            caps = {c: True for c in body["capabilities"]}
            a.capabilities = CapabilityState(caps, body.get("autonomy") or a.capabilities.admin_autonomy)
        if "user_enabled" in body:
            a.user_enabled = bool(body["user_enabled"])
        if body.get("proactive_delivery"):
            a.user_proactive_delivery = str(body["proactive_delivery"])

    def _handler(self, event: str, data: dict, body: dict):
        a = self.agent
        from hani2.support_agent.runtime import SupportAgent

        if event == "message":
            return lambda: a.handle_user_message(str(data.get("text") or ""))
        if event in ("negotiation_started", "action_requested", "negotiation_ended"):
            return lambda: a.on_event(event, None)
        if event == "draft_changed":
            return lambda: a.on_draft_changed(dict(data.get("draft") or {}))
        if event == "panel_action":
            return lambda: a.on_panel_action(str(data.get("panel_id") or ""), str(data.get("action") or ""),
                                             dict(data.get("payload") or {}))
        if event == "suggest_offer":
            return lambda: {"suggestion": a.suggest_offer(str(data.get("instruction") or ""),
                                                          str(data.get("mode") or "both"))}
        if event == "write_message":
            return lambda: {"suggestion": a.write_message(dict(data.get("offer") or {}) or None)}
        if event == "offer_from_message":
            return lambda: {"suggestion": a.offer_from_message(str(data.get("text") or ""))}
        if event == "clear":
            return a.clear_conversation
        if event == "autopilot":
            def _auto():
                a.autopilot = True
                if type(a)._run_autopilot_turn is not SupportAgent._run_autopilot_turn:
                    a._run_autopilot_turn()  # the class's own autopilot
                    return None
                note = ("(system) AUTOPILOT is engaged: it is your turn and NO human is watching. You MUST act now by "
                        "calling exactly one of submit_counter_offer, accept_offer, or end_negotiation.")
                a._run_turn(system_note=note, context_note=a._context_snapshot(), force_action=True)
                return None  # HANI2 counts stalls and sends the fallback counter-offer itself
            return _auto
        raise HostedError(f"unknown event {event!r}")

    def step(self, body: dict) -> dict:
        self._sync(body)
        event = str(body.get("event") or "")
        if event == "results":
            if self._pending is None:
                raise HostedError("no function call is waiting for results")
            self._inbox.put(list((body.get("data") or {}).get("results") or []))
            return self._wait()
        if self._turn_open and self._turn_thread is not None and self._turn_thread.is_alive():
            raise HostedError("the previous turn has not finished")
        fn = self._handler(event, dict(body.get("data") or {}), body)

        def _run() -> None:
            try:
                extra = fn()
                out = {"status": "done", "actions": self._flush()}
                if isinstance(extra, dict):
                    out.update(json_safe(extra))
            except Exception as e:  # noqa: BLE001
                if not isinstance(e, HostedError):
                    traceback.print_exc()
                out = {"status": "done", "actions": self._flush(), "error": f"{type(e).__name__}: {e}"}
            m = self.model_info()
            if m:
                out["model"] = m
            self._turn_open = False  # before the reply: the next event may arrive as soon as it is read
            self._outbox.put(out)

        self._turn_open = True
        self._turn_thread = threading.Thread(target=_run, daemon=True, name="hosted-assistant-turn")
        self._turn_thread.start()
        return self._wait()

    def _wait(self) -> dict:
        try:
            return self._outbox.get(timeout=STEP_WAIT)
        except queue.Empty:
            return {"status": "done", "actions": self._flush(), "error": "the Assistant took too long"}

    def close(self) -> None:
        if self._pending is not None:
            self._inbox.put({"__abort__": True})


__all__ = ["AssistantRunner", "ProxySession", "assistant_factory", "model_label"]
