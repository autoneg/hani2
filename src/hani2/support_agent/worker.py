"""The worker process of an isolated Assistant (see :mod:`hani2.support_agent.isolation`).

Run as ``python -I -m hani2.support_agent.worker``. It loads one Assistant class and runs it. The
class never gets the session: everything it does goes, as JSON lines, to the HANI2 server, which
runs it with the stock Assistant (capabilities, the information split and the recording apply
there) and answers with plain data.

Protocol (one JSON object per line; the server writes to this process's stdin and reads its stdout,
which carries nothing else: ``print`` goes to stderr):

- server → worker: ``{"t": "init", ...}``, ``{"t": "invoke", "id", "fn", "args", "state"}``,
  ``{"t": "result" | "error", "id", ...}`` (answers to the worker's calls);
- worker → server: ``{"t": "ready", ...}`` / ``{"t": "fatal", "error"}``, ``{"t": "call", "id", "fn",
  "args", "kwargs"}``, ``{"t": "result" | "error", "id", ...}`` (answers to invocations).
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
import uuid
from typing import Any

#: the base Assistant methods that run on the server (the stock implementation, for this session)
FORWARDED = (
    "context", "opponent_view", "post", "toast", "pin_message", "unpin_message", "show_on_board", "message_user",
    "ask_user", "highlight", "clear_highlights", "annotate", "set_layout", "set_offer_display", "set_interface",
    "set_presentation", "set_opponent_estimate", "focus_tool", "show_panel", "close_panel", "available_tools",
    "add_tool", "remove_tool", "read_tool", "use_tool", "private_information", "past_negotiation",
    "warn_if_draft_below_reserved", "_my_turn", "_viewer_is_admin",
)
#: what the server may ask the worker to do
#: the session's ``session_state["actions"]`` an isolated Assistant gets (run on the server)
ACTIONS = ("set_offer", "set_text", "get_offer", "get_partner_offer", "can_act", "context", "highlight", "accept",
           "end", "reject_counter")
INVOKABLE = ("handle_user_message", "on_event", "on_draft_changed", "on_panel_action", "autopilot_step",
             "clear_conversation", "execute", "schemas")


class IsolationError(RuntimeError):
    """Something an isolated Assistant cannot do (it has no session object)."""


class _Channel:
    def __init__(self, out) -> None:
        self.out = out
        self.lock = threading.Lock()
        self.pending: dict[str, dict[str, Any]] = {}
        self.cond = threading.Condition()

    def send(self, msg: dict) -> None:
        line = json.dumps(msg, default=_jsonable, allow_nan=True)
        with self.lock:
            self.out.write(line + "\n")
            self.out.flush()

    def call(self, fn: str, *args: Any, **kwargs: Any) -> Any:
        cid = "w" + uuid.uuid4().hex[:12]
        with self.cond:
            self.pending[cid] = {}
        self.send({"t": "call", "id": cid, "fn": fn, "args": list(args), "kwargs": kwargs})
        with self.cond:
            while not self.pending[cid]:
                self.cond.wait()
            reply = self.pending.pop(cid)
        if reply.get("t") == "error":
            raise IsolationError(str(reply.get("error")))
        return reply.get("value")

    def answer(self, msg: dict) -> None:
        with self.cond:
            if msg.get("id") in self.pending:
                self.pending[msg["id"]] = msg
                self.cond.notify_all()


def _jsonable(x: Any) -> Any:
    if isinstance(x, (set, frozenset, tuple)):
        return list(x)
    value = getattr(x, "value", None)  # enums
    if isinstance(value, (str, int, float)):
        return value
    return str(x)


CHANNEL: _Channel | None = None


def _rpc(fn: str, *args: Any, **kwargs: Any) -> Any:
    assert CHANNEL is not None
    return CHANNEL.call(fn, *args, **kwargs)


def _limits(cfg: dict) -> None:
    """Resource limits of this process (before any Assistant code is imported)."""
    try:
        import resource
    except ImportError:  # pragma: no cover - Windows
        return

    def _set(name: str, value: Any) -> None:
        lim = getattr(resource, name, None)
        if lim is None or value in (None, 0, ""):
            return
        try:
            soft, hard = resource.getrlimit(lim)
            v = int(value)
            if hard != resource.RLIM_INFINITY:
                v = min(v, hard)
            resource.setrlimit(lim, (v, v if hard == resource.RLIM_INFINITY else hard))
        except (ValueError, OSError):
            pass

    _set("RLIMIT_CORE", 1)  # setrlimit(…, 0) is skipped above; 1 byte is no core file either
    _set("RLIMIT_CPU", cfg.get("cpu_seconds"))
    mb = cfg.get("memory_mb")
    if mb and sys.platform.startswith("linux"):  # RLIMIT_AS breaks Python on macOS
        _set("RLIMIT_AS", int(mb) * 1024 * 1024)
    _set("RLIMIT_FSIZE", int(cfg.get("file_mb") or 64) * 1024 * 1024)
    _set("RLIMIT_NOFILE", cfg.get("open_files") or 256)


class _RemoteCapabilities:
    """The capability state lives on the server (the participant's switches change it there)."""

    def __init__(self, *_a: Any, **_kw: Any) -> None:
        pass

    def _caps(self, name: str, *args: Any) -> Any:
        return _rpc("caps", name, *args)

    def has(self, capability: Any) -> bool:
        return bool(self._caps("has", getattr(capability, "value", capability)))

    def effective(self) -> set:
        from hani2.support_agent.capabilities import Capability

        return {Capability(c) for c in self._caps("effective") or [] if c in Capability._value2member_map_}

    def autonomy_allows_execute(self, capability: Any) -> bool:
        return bool(self._caps("autonomy_allows_execute", getattr(capability, "value", capability)))

    def autonomy_allows_confirm(self, capability: Any) -> bool:
        return bool(self._caps("autonomy_allows_confirm", getattr(capability, "value", capability)))

    def _autonomy(self, name: str):
        from hani2.support_agent.capabilities import Autonomy

        return Autonomy.coerce(self._caps(name), Autonomy.SUGGEST)

    @property
    def autonomy(self):
        return self._autonomy("autonomy")

    @property
    def admin_autonomy(self):
        return self._autonomy("admin_autonomy")

    @admin_autonomy.setter
    def admin_autonomy(self, _v: Any) -> None:  # the server sets autonomy (autopilot)
        pass

    @property
    def user_autonomy(self):
        return self._autonomy("user_autonomy")

    @user_autonomy.setter
    def user_autonomy(self, _v: Any) -> None:
        pass

    @property
    def admin_capabilities(self) -> dict:
        return dict(self._caps("admin_capabilities") or {})

    def set_user_capability(self, *_a: Any) -> None:
        raise IsolationError("only the participant changes the Assistant's abilities")

    def set_user_autonomy(self, *_a: Any) -> None:
        raise IsolationError("only the participant changes the Assistant's autonomy")


def _patch_runtime() -> None:
    """Make the stock Assistant (in this process only) talk to the server instead of a session."""
    from hani2.support_agent import runtime, tools as dtools

    SA = runtime.SupportAgent

    def _no_session(self):
        raise IsolationError("this Assistant runs in its own process: it has no session object; use the "
                             "Assistant's methods (context(), post(), use_tool(), ...) instead")

    SA.session = property(_no_session)  # type: ignore[assignment]

    def _forward(name: str):
        def fn(self, *args, **kwargs):
            return _rpc(name, *args, **kwargs)

        fn.__name__ = name
        fn.__doc__ = getattr(getattr(SA, name, None), "__doc__", None)
        return fn

    for name in FORWARDED:
        setattr(SA, name, _forward(name))

    def run_on_doc(self, fn, timeout: float = 30.0):
        return fn()

    def _post_async(self, fn) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def _set_busy_state(self) -> None:
        try:
            _rpc("_set_busy_state", bool(self._busy.locked()))
        except Exception:  # noqa: BLE001
            pass

    def _complete(self, tools, force_action: bool = False, no_tools: bool = False) -> dict:
        return _rpc("complete", self.messages, tools, force_action, no_tools)

    def _harness_turn(self, tools, executed, output_channel: str = "chat", force_action: bool = False) -> bool:
        out = _rpc("harness", self.messages, tools, output_channel, force_action) or {}
        if not out.get("handled"):
            return False
        self.messages.extend(out.get("messages") or [])
        executed.update(out.get("executed") or [])
        return True

    def _autopilot_fallback(self) -> None:
        _rpc("_autopilot_fallback", int(self._autopilot_stalls))

    def set_autopilot(self, active: bool) -> None:
        self.autopilot = bool(active)  # the server switches autonomy

    def _unavailable(name: str):
        def fn(self, *a, **kw):
            raise IsolationError(f"{name} is not available to an isolated Assistant")

        return fn

    SA.run_on_doc = run_on_doc
    SA._post_async = _post_async
    SA._set_busy_state = _set_busy_state
    SA._complete = _complete
    SA._harness_turn = _harness_turn
    SA._autopilot_fallback = _autopilot_fallback
    SA.set_autopilot = set_autopilot
    SA.toolbox = _unavailable("toolbox")
    SA.model = _unavailable("model")
    SA.opponent_estimate = _unavailable("opponent_estimate")
    runtime.CapabilityState = _RemoteCapabilities  # type: ignore[misc]

    TD = dtools.ToolDispatcher

    def _builtin(self, name: str) -> bool:
        entry = self._registry.get(name)
        if entry is None:
            return False
        handler = entry[1]
        base = getattr(TD, getattr(handler, "__name__", ""), None)
        return getattr(handler, "__func__", None) is base and base is not None

    def schemas(self) -> list[dict]:
        out = list(_rpc("schemas") or [])
        have = {(s.get("function") or {}).get("name") for s in out}
        for name, (cap, _h, schema) in self._registry.items():
            if _builtin(self, name):
                continue
            if cap is not None and not self.caps.has(cap):
                continue
            s = schema()
            if name in have:  # a built-in name whose handler this Assistant replaced
                out = [x for x in out if (x.get("function") or {}).get("name") != name]
            out.append(s)
        return out

    def execute(self, name: str, args: dict) -> dict:
        if name not in self._registry or _builtin(self, name):
            return _rpc("dispatch", name, args or {})
        cap, handler, _ = self._registry[name]
        if cap is not None and not self.caps.has(cap):
            result = {"ok": False, "error": f"capability '{getattr(cap, 'value', cap)}' is not enabled"}
            self._record(name, args, result, 0.0)
            return result
        import time as _time

        t0 = _time.perf_counter()
        result = handler(args or {})
        self._record(name, args, result, _time.perf_counter() - t0)
        return result

    def _record(self, name: str, args: dict, result: Any, latency: float) -> None:
        try:
            _rpc("record", name, args or {}, result, float(latency))
        except Exception:  # noqa: BLE001
            pass

    TD.schemas = schemas
    TD.execute = execute
    TD._record = _record


def _action(name: str):
    def fn(*args, **kwargs):
        return _rpc("action", name, *args, **kwargs)

    fn.__name__ = name
    return fn


class Worker:
    def __init__(self) -> None:
        self.agent = None

    def init(self, msg: dict) -> dict:
        _limits(msg.get("limits") or {})
        for d in reversed(msg.get("syspath") or []):
            if d and d not in sys.path:
                sys.path.insert(0, d)
        _patch_runtime()
        from hani2.support_agent.runtime import load_assistant_class

        klass = load_assistant_class(str(msg["spec"]))
        state = dict(msg.get("state") or {})
        state["actions"] = {name: _action(name) for name in ACTIONS}
        self.agent = klass(state, dict(msg.get("settings") or {}))
        self._sync(msg.get("sync") or {})
        tools = list(getattr(klass, "tools", None) or [])
        pres = getattr(klass, "presentation", None)
        return {"name": str(getattr(self.agent, "name", "Assistant")),
                "presentation": pres if isinstance(pres, dict) else None,
                "refused_tools": [getattr(t, "__name__", str(t)) for t in tools]}

    def _sync(self, st: dict) -> None:
        a = self.agent
        if a is None:
            return
        if "user_enabled" in st:
            a.user_enabled = bool(st["user_enabled"])
        if "autopilot" in st:
            a.autopilot = bool(st["autopilot"])
        if "proactive_delivery" in st:
            a.user_proactive_delivery = str(st["proactive_delivery"])

    def invoke(self, fn: str, args: list, state: dict) -> Any:
        if fn not in INVOKABLE:
            raise IsolationError(f"cannot invoke {fn!r}")
        self._sync(state or {})
        a = self.agent
        if fn == "execute":
            return a.dispatcher.execute(str(args[0]), dict(args[1] or {}))
        if fn == "schemas":
            return a.dispatcher.schemas()
        if fn == "on_event":
            return a.on_event(str(args[0]), None)  # no nmi: it reaches the mechanism
        return getattr(a, fn)(*args)


def main() -> None:
    global CHANNEL
    # the protocol owns the original stdout; everything printed goes to stderr
    out = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    CHANNEL = _Channel(out)
    worker = Worker()
    stdin = sys.stdin

    def _run(msg: dict) -> None:
        try:
            value = worker.invoke(str(msg.get("fn")), list(msg.get("args") or []), msg.get("state") or {})
            CHANNEL.send({"t": "result", "id": msg.get("id"), "value": value})
        except BaseException as e:  # noqa: BLE001
            traceback.print_exc()
            CHANNEL.send({"t": "error", "id": msg.get("id"), "error": f"{type(e).__name__}: {e}"})

    def _init(msg: dict) -> None:
        try:
            CHANNEL.send({"t": "ready", **worker.init(msg)})
        except BaseException as e:  # noqa: BLE001
            traceback.print_exc()
            CHANNEL.send({"t": "fatal", "error": f"{type(e).__name__}: {e}"})
            os._exit(1)

    for line in stdin:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = msg.get("t")
        if t == "init":  # in a thread: creating the Assistant already asks the server (capabilities)
            threading.Thread(target=_init, args=(msg,), daemon=True).start()
        elif t == "invoke":
            threading.Thread(target=_run, args=(msg,), daemon=True).start()
        elif t in ("result", "error"):
            CHANNEL.answer(msg)
        elif t == "exit":
            break
    os._exit(0)  # stdin closed: the server is gone (or dropped this Assistant)


if __name__ == "__main__":
    main()
