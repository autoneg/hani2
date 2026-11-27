"""``RemoteAssistant``: an Assistant whose decisions are made by a team's host.

To the session it is an ordinary :class:`~hani2.support_agent.runtime.Assistant`: the same entry points
(chat messages, negotiation events, the draft, panel clicks, the LLM offer tool, the autopilot). Each
is forwarded as one event to the host with the same ``context`` a local Assistant reads. The host
answers with ``actions`` (fire and forget: ``post``, ``toast``, ``show_on_board``, ``highlight``, …)
and ``calls`` (functions whose results it needs, such as ``get_negotiation_state`` or
``submit_counter_offer``). HANI2 runs every one of them **here**, through the Assistant helpers and the
function dispatcher, so the admin's capabilities, the participant's switches and the autonomy level
apply exactly as for a local Assistant. Results go back in a ``results`` event until the host says
``done``.

One host session per negotiation (one Assistant object spans the negotiations of a browser session).
A turn has a deadline (``turn_deadline``) and always releases the busy lock; a failing host shows a
message in the chat and never blocks the negotiation. The Assistant never uses HANI2's model chain:
the host brings its own model and may report it (``model``), which the results record unverified.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from typing import Any

from hani2.hosting.client import HostedClient
from hani2.hosting.protocol import (PROTOCOL, HostedError, encode_outcome_space, issue_names, json_safe, model_label,
                                    recorded_spec)
from hani2.support_agent.runtime import SupportAgent, _executed_name

_CLASSES: dict[str, type] = {}

#: fire-and-forget actions a host may send: the Assistant helper they run (with its own capability checks)
ACTIONS = ("post", "toast", "show_on_board", "message_user", "pin_message", "unpin_message", "highlight",
           "clear_highlights", "annotate", "set_layout", "set_offer_display", "set_interface", "set_presentation",
           "set_opponent_estimate", "focus_tool", "show_panel", "close_panel", "set_autopilot")
#: events the host gets only when it asks for them (``events`` in its replies or /info);
#: ``action_requested`` also when the admin turned on the proactive note for it
OPTIONAL_EVENTS = ("draft_changed", "action_requested")
MAX_CALLS_PER_REPLY = 10
#: what :meth:`RemoteAssistant._run_action` returns for a name that is a function, not an action
NOT_AN_ACTION = object()
MAX_RESULT_CHARS = 20000


class RemoteAssistant(SupportAgent):
    """An Assistant that runs on a team's own host (see :mod:`hani2.hosting`)."""

    #: the hosted spec of the bound subclass
    spec: str = ""
    is_remote = True
    #: the host brings its own language model: the session never resolves the Assistant's chain for it
    brings_own_model = True
    #: seconds one turn may take, every round trip and function call included
    turn_deadline: float = 120.0

    def __init__(self, session_state: dict[str, Any], settings: dict):
        from hani2.hosting import registry

        super().__init__(session_state, settings)
        self.endpoint = registry.resolve(self.spec, kind="assistant")
        self.turn_deadline = max(float(self.endpoint.timeout), min(float(self.turn_deadline), 600.0))
        self._client: HostedClient | None = None
        self._sid: str | None = None
        self._seq = 0
        self._wants: set[str] = set()
        self.failures_total = 0
        self.last_error = ""
        self.reported_model = ""
        self.declared_version = ""
        self._lifecycle = threading.Lock()
        self._record()

    # -- attribution ----------------------------------------------------------
    def _record(self) -> None:
        try:
            self.session_state["hosted_assistant"] = {"name": recorded_spec(self.spec), "model": self.reported_model,
                                                      "version": self.declared_version,
                                                      "failures": self.failures_total, "error": self.last_error}
        except Exception:  # noqa: BLE001
            pass

    def model(self):
        """``None``: a hosted Assistant brings its own model (HANI2's chain is never used for it)."""
        return None

    def _note(self, reply: dict) -> None:
        changed = False
        if reply.get("model"):
            m = model_label(reply["model"])
            changed = changed or m != self.reported_model
            self.reported_model = m
        if reply.get("version"):
            v = str(reply["version"])[:60]
            changed = changed or v != self.declared_version
            self.declared_version = v
        if isinstance(reply.get("events"), list):
            self._wants = {str(e) for e in reply["events"] if e in OPTIONAL_EVENTS}
        if changed:
            self._record()

    # -- the host session -----------------------------------------------------
    @property
    def client(self) -> HostedClient:
        if self._client is None:
            self._client = HostedClient(self.endpoint)
        return self._client

    def _setup(self) -> dict:
        s = self.session
        os_ = s.scenario.outcome_space if getattr(s, "scenario", None) is not None else None
        return json_safe({
            "protocol": PROTOCOL, "name": self.name,
            "outcome_space": encode_outcome_space(os_) if os_ is not None else None,
            "issues": issue_names(os_) if os_ is not None else [],
            "settings": {k: self.settings.get(k) for k in ("proactive", "max_tool_iterations")},
            **self._state_info(),
        })

    def _state_info(self) -> dict:
        caps = self.capabilities
        return {"capabilities": sorted(c.value for c in caps.effective()), "autonomy": caps.autonomy.value,
                "user_enabled": self.user_enabled, "autopilot": self.autopilot,
                "proactive_delivery": self.user_proactive_delivery,
                "functions": self.dispatcher.schemas()}

    def _ensure_session(self) -> str:
        with self._lifecycle:
            if self._sid is None:
                sid = "a-" + uuid.uuid4().hex
                reply = self.client.create(sid, "assistant", self._setup())
                if reply.get("ok") is False:
                    raise HostedError(f"the hosted agent {self.endpoint.name} refused the session: "
                                      f"{str(reply.get('error') or '')[:200]}")
                self._sid, self._seq = sid, 0
                self._note(reply)
            return self._sid

    def _close_session(self) -> None:
        with self._lifecycle:
            sid, self._sid = self._sid, None
        if sid is None:
            return
        client = self.client

        def _end() -> None:
            try:
                client.end(sid)
            except HostedError:
                pass

        threading.Thread(target=_end, daemon=True, name="hosted-close").start()

    # -- running what the host asks ---------------------------------------------
    def _run_action(self, a: dict, output_channel: str) -> Any:
        name = str(a.get("action") or a.get("function") or a.get("name") or "")
        args = a.get("arguments") if isinstance(a.get("arguments"), dict) else {
            k: v for k, v in a.items() if k not in ("action", "function", "name", "id")}
        if name == "say":
            self._deliver_assistant_message(str(args.get("text") or ""), channel=str(args.get("channel") or output_channel))
            return {"ok": True}
        if name in ACTIONS:
            if name == "set_autopilot":  # the host may only switch the autopilot off (hand control back)
                if not args.get("active", args.get("on", False)):
                    self.session.set_autopilot(False)
                    return {"ok": True}
                return {"ok": False, "error": "a hosted Assistant cannot switch the autopilot on"}
            if name == "post":
                args = {"text": args.get("text", "")}  # never another author (``user``)
            try:
                return getattr(self, name)(**args)
            except TypeError as e:
                return {"ok": False, "error": f"{name}: {e}"}
        return NOT_AN_ACTION

    def _run_call(self, c: dict, executed: set[str], output_channel: str) -> Any:
        fn = c.get("function")
        if isinstance(fn, dict):  # OpenAI style {"function": {"name", "arguments"}}
            name, raw = str(fn.get("name") or ""), fn.get("arguments")
        else:
            name, raw = str(fn or c.get("name") or c.get("action") or ""), c.get("arguments")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw or "{}")
            except json.JSONDecodeError:
                return {"ok": False, "error": "arguments are not valid JSON"}
        args = raw if isinstance(raw, dict) else {}
        res = self._run_action({"action": name, "arguments": args}, output_channel)
        if res is NOT_AN_ACTION:
            try:
                res = self.dispatcher.execute(name, args)
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        executed.add(_executed_name(name, res))
        out = json_safe(res)
        text = json.dumps(out, default=str)
        if len(text) > MAX_RESULT_CHARS:
            out = {"ok": isinstance(res, dict) and res.get("ok", True), "truncated": True, "text": text[:MAX_RESULT_CHARS]}
        return out

    def _context_safe(self) -> dict | None:
        try:
            return json_safe(self.context())
        except Exception:  # noqa: BLE001
            return None

    def _turn(self, event: str, data: dict | None = None, *, force_action: bool = False,
              output_channel: str = "chat", wait: float = 0.0, quiet: bool = False) -> tuple[set[str], dict]:
        """One event to the host and the round trips it asks for. Returns ``(executed, last reply)``."""
        executed: set[str] = set()
        reply: dict = {}
        got = self._busy.acquire(timeout=wait) if wait > 0 else self._busy.acquire(blocking=False)
        if not got:
            if not force_action and not quiet:
                self.post("(I'm still working on the previous request — one moment.)")
            return executed, reply
        self._set_busy_state()
        try:
            sid = self._ensure_session()
            deadline = time.time() + self.turn_deadline
            body: dict[str, Any] = {"event": event, "data": json_safe(data or {}), "context": self._context_safe(),
                                    "output_channel": output_channel, "force_action": force_action,
                                    **self._state_info()}
            rounds = 2 * int(self.settings.get("max_tool_iterations", 10)) + 2
            for _ in range(rounds):
                left = deadline - time.time()
                if left <= 0:
                    raise HostedError(f"the hosted agent {self.endpoint.name} took longer than "
                                      f"{self.turn_deadline:g} s for one turn")
                self._seq += 1
                reply = self.client.step(sid, {"seq": self._seq, **body}, timeout=min(left, self.endpoint.timeout))
                self._note(reply)
                for a in (reply.get("actions") or [])[:50]:
                    if isinstance(a, dict):
                        res = self._run_action(a, output_channel)
                        if res is NOT_AN_ACTION:  # a function sent as an action: run it, ignore the result
                            self._run_call(a, executed, output_channel)
                if reply.get("say"):
                    self._deliver_assistant_message(str(reply["say"]), channel=output_channel)
                calls = [c for c in (reply.get("calls") or []) if isinstance(c, dict)][:MAX_CALLS_PER_REPLY]
                if reply.get("status", "done") != "calls" or not calls:
                    if reply.get("error") and not quiet:
                        self.post(f"⚠️ The Assistant reported an error: {str(reply['error'])[:300]}")
                    return executed, reply
                results = [{"id": c.get("id"), "result": self._run_call(c, executed, output_channel)} for c in calls]
                body = {"event": "results", "data": {"results": results}, "context": None, **self._state_info()}
            raise HostedError(f"the hosted agent {self.endpoint.name} asked for more than {rounds} rounds in one turn")
        except HostedError as e:
            self.failures_total += 1
            self.last_error = str(e)
            self._record()
            print(f"[hani2] hosted Assistant {self.endpoint.name}: {e}")
            if not force_action and not quiet:
                self.post(f"⚠️ The Assistant could not answer: {e}")
            if "no session" in str(e) or "HTTP 404" in str(e):
                with self._lifecycle:
                    self._sid = None  # the host forgot the session (restarted, expired): open a new one next time
            return executed, reply
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.failures_total += 1
            self.last_error = f"{type(e).__name__}: {e}"
            self._record()
            if not force_action and not quiet:
                self.post(f"⚠️ Assistant error: {type(e).__name__}")
            return executed, reply
        finally:
            self._busy.release()
            self._set_busy_state()

    # -- entry points called by the session ---------------------------------------
    def handle_user_message(self, text: str) -> None:
        if not self.user_enabled:
            self.post("(The assistant is turned off. Switch it on to chat.)")
            return
        if self._answer_question(text):
            return
        self._turn("message", {"text": str(text)}, wait=20.0)  # an event turn may still be running

    def on_event(self, event_name: str, nmi=None) -> None:
        if event_name == "action_requested":
            self._below_reserved_warned = False
        if event_name == "negotiation_started":
            self._close_session()  # a new negotiation: a new host session
        try:
            if not self.user_enabled:
                return
            channel = self.user_proactive_delivery if self.user_proactive_delivery in ("toast", "board", "chat") else "toast"
            lifecycle = event_name in ("negotiation_started", "negotiation_ended")
            proactive = (self.settings.get("proactive") or {}).get(f"on_{event_name}", False)
            if not lifecycle and event_name not in self._wants and not proactive:
                return
            self._turn(event_name, {}, output_channel=channel, wait=10.0 if lifecycle else 0.0,
                       quiet=event_name != "negotiation_started")
        finally:
            if event_name == "negotiation_ended":
                self._close_session()

    def on_draft_changed(self, draft: dict[str, Any]) -> None:
        self.warn_if_draft_below_reserved()
        if "draft_changed" in self._wants and self.user_enabled:
            self._turn("draft_changed", {"draft": json_safe(draft)}, quiet=True)  # skipped while busy: coalesced

    def on_panel_action(self, panel_id: str, action: str, payload: dict[str, Any]) -> None:
        if self.user_enabled:
            self._turn("panel_action", {"panel_id": panel_id, "action": action, "payload": json_safe(payload)})

    def suggest_offer(self, instruction: str, mode: str = "both", timeout: float = 120.0) -> dict | None:
        if not self.answers_llm_tool(mode):
            return None
        _, reply = self._turn("suggest_offer", {"instruction": str(instruction), "mode": mode},
                              wait=min(timeout, 30.0), quiet=True)
        sug = reply.get("suggestion") if isinstance(reply, dict) else None
        if sug is None:
            return {"outcome": None, "text": None, "error": self.last_error or "The Assistant gave no suggestion."} \
                if not reply else None
        if not isinstance(sug, dict):
            return {"outcome": None, "text": None, "error": "The Assistant's suggestion was not understood."}
        outcome = sug.get("outcome")
        if outcome is not None:
            o = self.session.offer_outcome(outcome) if isinstance(outcome, dict) else None
            if o is None:
                return {"outcome": None, "text": None, "error": "The Assistant suggested an invalid offer."}
            outcome = self.session.outcome_to_dict(o)
        text = sug.get("text")
        return {"outcome": outcome, "text": str(text)[:4000] if text is not None else None,
                "error": str(sug["error"])[:300] if sug.get("error") else None}

    def _run_autopilot_turn(self) -> None:
        acted, _ = self._turn("autopilot", {}, force_action=True, wait=5.0)
        if acted & self._ACTION_TOOLS:
            self._autopilot_stalls = 0
            return
        self._autopilot_stalls += 1
        self._autopilot_fallback()

    def clear_conversation(self) -> None:
        super().clear_conversation()
        threading.Thread(target=lambda: self._turn("clear", {}, quiet=True), daemon=True).start()


def remote_assistant_class(spec: Any) -> type:
    """A :class:`RemoteAssistant` subclass bound to ``spec`` (one per spec; the endpoint is looked up
    when the Assistant is made)."""
    from hani2.hosting.protocol import normalise_spec, short_label

    spec = str(normalise_spec(spec)).strip()
    k = _CLASSES.get(spec)
    if k is None:
        safe = "".join(ch if ch.isalnum() else "_" for ch in short_label(spec))[:40]
        k = type(f"Remote_{safe}", (RemoteAssistant,), {"spec": spec, "__module__": __name__})
        _CLASSES[spec] = k
    return k
