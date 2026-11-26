"""The Assistant runtime.

:class:`Assistant` is the class of the Assistant; :class:`SupportAgent` is its
old name (the same class). One :class:`SupportAgent` lives in each session (``session_state["support_agent"]``).
It owns the conversation with its language model, the capability state, and the
multi-turn tool-calling loop, and it can reach the participant at any moment
(chat, notifications, the status board, highlights, notes, layout changes and
custom panels).

All agent code runs in worker threads, so it may block (LLM calls, ``ask_user``)
without freezing the interface. Use :meth:`SupportAgent.run_on_doc` to read or
change interface-owned state atomically.

Build your own agent by subclassing :class:`SupportAgent` and pointing
``assistant_settings.json`` → ``agent_class`` at it
(``"my_module:MyAgent"``).
"""

from __future__ import annotations

import contextlib

import importlib
import sys
import json
import re
import threading
import traceback
import uuid
from typing import TYPE_CHECKING, Any

from hani2.support_agent.capabilities import ADMIN_ONLY_CAPABILITIES, CAPABILITY_INFO, Autonomy, Capability, CapabilityState
from hani2.support_agent.settings import load_support_agent_settings, support_agent_enabled
from hani2 import events as ev
from hani2.support_agent.tools import ToolDispatcher, _log_agent_action

if TYPE_CHECKING:  # pragma: no cover
    from hani2.session import NegotiationSession

__all__ = ["Assistant", "SupportAgent", "AssistantLoadError", "resolve_agent_class", "load_assistant_class",
           "create_assistant_for", "create_support_agent_for", "flatten_tool_messages"]

_VALID_TOAST_LEVELS = {"info", "success", "warning", "error"}
_VALID_PROACTIVE_DELIVERY = {"toast", "board", "chat"}
AGENT_NAME = "Assistant"


def flatten_tool_messages(messages: list[dict]) -> list[dict]:
    """Express tool calls and results as plain text (needed for Ollama models,
    whose chat transform drops ``tool_calls`` from assistant messages)."""
    out: list[dict] = []
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            calls = "; ".join(
                f'{t["function"]["name"]}({t["function"].get("arguments") or "{}"})' for t in m["tool_calls"]
            )
            out.append({"role": "assistant", "content": ((m.get("content") or "") + f"\n[tool call: {calls}]").strip()})
        elif role == "tool":
            out.append({"role": "user", "content": f'[tool result: {m.get("name", "tool")}] {m.get("content", "")}'})
        else:
            out.append(m)
    return out


_TEXT_CALL = re.compile(r"\[tool call:\s*([A-Za-z_][\w]*)\((.*?)\)\]", re.DOTALL)


def parse_text_tool_calls(content: str) -> list[dict]:
    """Recover tool calls a model wrote as text (``[tool call: name({...})]``).

    Small local models sometimes imitate the flattened history format instead
    of emitting real tool calls; this turns them back into calls."""
    calls = []
    for i, m in enumerate(_TEXT_CALL.finditer(content or "")):
        args = m.group(2).strip() or "{}"
        try:
            json.loads(args)
        except json.JSONDecodeError:
            continue
        calls.append({"id": f"text-{uuid.uuid4().hex[:6]}-{i}", "type": "function",
                      "function": {"name": m.group(1), "arguments": args}})
    return calls


#: added to the system prompt when the ``opponent_utility`` capability (the oracle) is granted
ORACLE_PROMPT = """OPPONENT KNOWLEDGE: in this session you know the opponent's utility function. The state you \
are given has an "opponent" entry with its preferences (opponent_preferences), its reserved value and its \
utility of the offers on the table and in the history; get_opponent_utility scores any offer for both sides. \
Use it to find offers the opponent will accept that are as good as possible for the human. Never tell the \
opponent, or hint in the message to the opponent, that you know its preferences."""


class SupportAgent:
    """Base Assistant (``Assistant``; ``SupportAgent`` is the old name of this class).

    Override any of these (all optional):

    * :meth:`build_system_prompt` — the agent's persona / instructions.
    * ``dispatcher_class`` / :meth:`make_dispatcher` — add or change the
      functions the language model may call.
    * :meth:`handle_user_message` — full control over a chat turn (e.g. a
      rule-based agent with no LLM at all).
    * :meth:`on_event` / :meth:`proactive_note` — react to negotiation events
      (``negotiation_started``, ``action_requested``, ``negotiation_ended``).
    * :meth:`on_draft_changed` — react while the human edits their offer.
    * :meth:`on_panel_action` — a button in one of your panels was clicked.
    * :meth:`_complete` — replace the LLM backend.
    """

    #: Set to a ToolDispatcher subclass to add custom functions.
    dispatcher_class: type[ToolDispatcher] = ToolDispatcher
    #: Tools this agent brings: ``Tool`` subclasses (or ``"module:Class"`` /
    #: ``"path/to/file.py:Class"`` strings). They are not shown until the
    #: agent calls :meth:`add_tool`; the language model can add them by name.
    tools: list = []
    #: The name shown in the chat.
    name: str = AGENT_NAME
    #: How this Assistant appears from the start, applied when it is created (before the page
    #: shows it): any of ``style`` (panel | persona | both), ``may_hide`` and ``may_show`` (may the
    #: participant hide the character, or bring it back). ``None`` leaves it to the admin's
    #: settings. Needs the ``presentation`` capability; see :meth:`set_presentation`.
    presentation: dict[str, Any] | None = None

    def __init__(self, session_state: dict[str, Any], settings: dict):
        self.session_state = session_state
        self.settings = settings
        self.capabilities = CapabilityState(
            admin_capabilities=settings.get("capabilities", {}),
            admin_autonomy=settings.get("autonomy", "suggest"),
        )
        prompt = self.build_system_prompt()
        if self.capabilities.has(Capability.OPPONENT_UTILITY):
            prompt = prompt + "\n\n" + ORACLE_PROMPT
        self.messages: list[dict] = [{"role": "system", "content": prompt}]
        self._busy = threading.Lock()
        self.dispatcher = self.make_dispatcher()
        default_enabled = bool(session_state.get("support_agent_default_enabled", True))
        self.user_enabled = bool(session_state.get("support_agent_user_enabled", default_enabled))
        session_state["support_agent_user_enabled"] = self.user_enabled
        self.autopilot = False
        self._saved_autonomy: tuple | None = None
        self._autopilot_stalls = 0
        self.user_proactive_delivery = str(session_state.get("support_proactive_delivery", "toast"))
        self._pending_question: dict[str, Any] | None = None
        self._below_reserved_warned = False
        if self.presentation and self.capabilities.has(Capability.PRESENTATION):
            p = self.presentation
            ov = {k: p[k] for k in ("style", "may_hide", "may_show") if p.get(k) is not None}
            if ov.get("style") not in (None, "panel", "persona", "both"):
                ov.pop("style")
            session_state["assistant_presentation_override"] = ov
            sess = session_state.get("_session")
            if sess is not None and (ov.get("style") in ("persona", "both") or ov.get("may_hide") is False):
                sess.prefs["persona_hidden"] = False  # as set_presentation: this Assistant wants to be seen

    # ------------------------------------------------------------------ #
    # Session helpers                                                      #
    # ------------------------------------------------------------------ #
    @property
    def session(self) -> "NegotiationSession":
        return self.session_state["_session"]

    @property
    def busy(self) -> bool:
        return self._busy.locked()

    def build_system_prompt(self) -> str:
        return str(self.settings.get("system_prompt", ""))

    def make_dispatcher(self) -> ToolDispatcher:
        return self.dispatcher_class(self)

    def run_on_doc(self, fn, timeout: float = 30.0):
        """Run ``fn`` atomically with respect to the interface state and return its result."""
        return self.session.run_on_doc(fn, timeout)

    def _post_async(self, fn) -> None:
        """Fire-and-forget version of :meth:`run_on_doc`."""
        self.session.submit(self.session.run_on_doc, fn)

    def context(self) -> dict[str, Any]:
        """The live negotiation snapshot (issues, offers, utilities, history…); with the
        ``opponent_utility`` capability also the opponent's preferences and utilities (``opponent``)."""
        ctx = self.run_on_doc(self.session.context)
        if isinstance(ctx, dict) and self.capabilities.has(Capability.OPPONENT_UTILITY):
            try:
                ctx["opponent"] = self.run_on_doc(self.session.opponent_context)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
        return ctx

    def opponent_view(self, offer: dict[str, Any] | None = None) -> dict:
        """The opponent's preferences and its utility of the offers on the table (the oracle);
        with ``offer`` (``{issue: value}``) also both sides' utility of that offer. Needs
        ``opponent_utility`` (admin-only; off by default)."""
        denied = self._denied(Capability.OPPONENT_UTILITY)
        if denied:
            return denied
        s = self.session

        def _view():
            out = {"ok": True, **s.opponent_context()}
            if offer is not None:
                o = s.offer_outcome(offer)
                if o is None:
                    return {"ok": False, "error": "offer must give a valid value for every issue",
                            "issues": [i.name for i in s.issues]}
                out["offer"] = dict(offer=s.display_outcome(s.outcome_to_dict(o)), opponent_utility=s.opponent_utility(o),
                                    your_utility=s.utility(o))
            return out

        return self.run_on_doc(_view)

    # ------------------------------------------------------------------ #
    # Talking to the human                                                 #
    # ------------------------------------------------------------------ #
    def post(self, text: str, user: str | None = None) -> None:
        """Post a chat message from the agent."""
        self.session.add_chat(user or self.name, str(text))

    def toast(self, message: str, level: str = "info") -> bool:
        """A pop-up notification (needs the ``toast`` capability; falls back to chat)."""
        level = level if level in _VALID_TOAST_LEVELS else "info"
        if not self.capabilities.has(Capability.TOAST):
            self.post(message)
            return False
        return self.session.toast(message, level, source="assistant")

    def pin_message(self, text: str, position: str = "top", level: str = "info", pin_id: str | None = None,
                    dismissible: bool = True) -> dict:
        """Pin a markdown message above (``top``) or below (``bottom``) the negotiation (needs the
        ``pin`` capability). The screen shrinks to make room, so nothing is covered. Reusing a
        ``pin_id`` replaces that pin. Returns ``{"ok", "id"}``."""
        if not self.capabilities.has(Capability.PIN):
            return {"ok": False, "error": "pinning messages is not allowed"}
        return self.session.pin(text, position=position, level=level, pin_id=pin_id, dismissible=dismissible)

    def unpin_message(self, pin_id: str | None = None) -> dict:
        """Remove a pinned message (``None``: all of them)."""
        if not self.capabilities.has(Capability.PIN):
            return {"ok": False, "error": "pinning messages is not allowed"}
        return self.session.unpin(pin_id, by="assistant")

    def show_on_board(self, text: str, append: bool = False) -> bool:
        """Write markdown to the always-visible status board."""
        s = self.session
        with s.lock:
            s.board = (s.board + "\n\n" + text) if (append and s.board) else str(text)
        s.push_state()
        return True

    def message_user(self, text: str, channel: str = "chat") -> None:
        """Tell the human something right now: ``chat``, ``toast`` or ``board``."""
        if channel == "toast":
            self.toast(text, "info")
        elif channel == "board":
            self.show_on_board(text)
        else:
            self.post(text)

    def ask_user(self, question: str, options: list[str] | None = None, timeout: float = 180.0) -> str | None:
        """Ask the human a question and block until they answer (buttons or typed
        reply). Returns ``None`` on timeout, under autopilot, or if another
        question is pending."""
        if self.autopilot or self._pending_question is not None:
            return None
        s = self.session
        pending = {"id": uuid.uuid4().hex[:8], "event": threading.Event(), "answer": None}
        self._pending_question = pending
        with s.lock:
            s.pending_question = {"id": pending["id"], "question": question, "options": [str(o) for o in options or []]}
        s.add_chat(self.name, question, kind="question", extra={"options": [str(o) for o in options or []],
                                                                 "question_id": pending["id"]})
        s.push_state()
        try:
            pending["event"].wait(timeout)
            return pending["answer"]
        finally:
            self._pending_question = None
            with s.lock:
                s.pending_question = None
            s.push_state()

    def _answer_question(self, answer: str, echo: bool = False) -> bool:
        pending = self._pending_question
        if pending is None:
            return False
        pending["answer"] = answer
        if echo:
            self.session.add_chat("You", answer)
        pending["event"].set()
        return True

    # -- interface control -------------------------------------------------
    # These helpers respect the effective capabilities (admin grant ∩ the
    # participant's switches): when a capability is off they do nothing and
    # return ``{"ok": False, "error": ...}``.
    def _denied(self, cap: Capability) -> dict | None:
        if self.capabilities.has(cap):
            return None
        return {"ok": False, "error": f"capability '{cap.value}' is not enabled"}

    def highlight(self, target: str, message: str | None = None, style: str = "pulse",
                  duration: float | None = None) -> dict:
        """Spotlight an element (``"accept"``, ``"issue:Price"``, ``"tool:Utility Plot"`` …).
        Needs the ``highlight`` capability."""
        return self._denied(Capability.HIGHLIGHT) or self.session.highlight(
            target, message=message, style=style, duration=duration)

    def clear_highlights(self, target: str | None = None) -> dict:
        return self.session.clear_highlights(target)

    def annotate(self, target: str, text: str | None, kind: str = "info") -> dict:
        """Attach a note to an element; ``text=None`` removes it. Needs ``annotate``."""
        if text is None:
            return self.session.annotate(target, None)
        return self._denied(Capability.ANNOTATE) or self.session.annotate(target, text, kind)

    def set_layout(self, **changes: Any) -> dict:
        """``view`` (full | simple | focus | bare), ``collapsed``, ``sizes``. Needs ``layout``."""
        return self._denied(Capability.LAYOUT) or self.session.set_layout(**changes)

    def set_offer_display(self, **changes: Any) -> dict:
        """Change how offers read (``offer_template``, ``issue_format``, ``value_labels``,
        ``issue_widget``, ``offer_display``, ``reset``); see
        :meth:`hani2.session.NegotiationSession.set_offer_display`. Needs ``offer_display``."""
        return self._denied(Capability.OFFER_DISPLAY) or self.session.set_offer_display(**changes)

    def set_interface(self, prefs: dict | None = None, custom_css: str | None = None) -> dict:
        """Change the participant's display settings (``prefs``) and the page's extra style sheet
        (``custom_css``); see :meth:`hani2.session.NegotiationSession.set_interface`. Needs
        ``interface``."""
        return self._denied(Capability.INTERFACE) or self.session.set_interface(prefs=prefs, custom_css=custom_css)

    def set_presentation(self, style: str | None = None, *, may_hide: bool | None = None,
                         may_show: bool | None = None, clear: bool = False) -> dict:
        """Decide how the Assistant appears: ``style`` panel (the header's Assistant button only),
        persona (the character only) or both; ``may_hide`` / ``may_show``: whether the participant
        may hide the character or bring it back once hidden. ``clear=True`` hands the decision back
        to the admin's settings. Needs ``presentation``."""
        return self._denied(Capability.PRESENTATION) or self.session.set_assistant_presentation(
            style, may_hide=may_hide, may_show=may_show, clear=clear)

    def set_opponent_estimate(self, estimate: Any = None) -> dict:
        """Share an estimate of the opponent's utility function: a negmas utility function over
        the scenario's outcome space, or a mapping with ``weights`` (issue → number), ``values``
        (issue → {option: number}, or ``"increasing"`` / ``"decreasing"``) and ``reserved_value``.
        ``None`` clears it. It goes into the human negotiator's ``opponent_ufun``, and while it is
        set the participant's Negotiation Plot and Utility-based Selector show it, marked as an
        estimate. It lasts until the next scenario. Needs ``opponent_model``."""
        return self._denied(Capability.OPPONENT_MODEL) or self.session.set_opponent_estimate(estimate, by="assistant")

    def opponent_estimate(self) -> Any:
        """The estimate of the opponent's utility function now set (by anyone), or ``None``."""
        return self.session.opponent_ufun_estimate

    def focus_tool(self, name: str) -> dict:
        """Bring a tool to the front. Needs ``tool_visibility``."""
        return self._denied(Capability.TOOL_VISIBILITY) or self.session.tool_controller.focus_tool(name)

    def show_panel(self, panel_id: str, title: str, components: list, placement: str = "assistant") -> dict:
        """Show a panel built from :mod:`hani2.tools.ui` components. Buttons and
        table selections in it call :meth:`on_panel_action`. Needs ``panels``."""
        return self._denied(Capability.PANELS) or self.session.show_panel(
            panel_id, title, components, placement=placement)

    def close_panel(self, panel_id: str | None = None) -> dict:
        return self.session.close_panel(panel_id)

    # -- tools: discover, read, use, add ---------------------------------
    def toolbox(self) -> dict[str, type]:
        """Tools the agent may add now, by name: its own :attr:`tools`, the
        ``toolbox`` setting, and registered tools the participant does not
        have yet. Admin-only, guest and ``tools.disabled`` rules apply."""
        from hani2.config import get_env
        from hani2.tools.registry import addable_tool_specs, import_tool

        sess = self.session
        present = {t.name.lower() for t in sess.tools}
        disabled = {str(x).lower() for x in (get_env("tools.disabled", []) or [])}
        out: dict[str, type] = {}
        for item in list(self.tools or []) + list(self.settings.get("toolbox") or []):
            try:
                cls = import_tool(item) if isinstance(item, str) else item
            except Exception as e:  # noqa: BLE001
                print(f"[hani2] Assistant tool {item!r} could not be loaded: {e}")
                continue
            name = getattr(cls, "name", "") or cls.__name__
            if name.lower() in present or name.lower() in disabled:
                continue
            if getattr(cls, "admin_only", False) and not sess.is_admin:
                continue
            if not getattr(cls, "guest", True) and sess.mode == "guest":
                continue
            out.setdefault(name, cls)
        for spec in addable_tool_specs(sess):
            out.setdefault(spec.name, spec.cls)
        return out

    def available_tools(self) -> list[dict[str, Any]]:
        """``[{name, description, pane}]`` of the tools :meth:`add_tool` accepts by name."""
        return [dict(name=n, description=getattr(c, "description", ""), pane=getattr(c, "pane", "upper"),
                     hint=getattr(c, "agent_hint", "")) for n, c in self.toolbox().items()]

    def add_tool(self, tool: Any, *, pane: str | None = None, at_front: bool = True, focus: bool = True) -> dict:
        """Add a tool to the participant's screen now. ``tool`` is a name from
        :meth:`available_tools`, a ``Tool`` subclass or an instance. It stays
        for the rest of the session. Needs ``tool_add``."""
        denied = self._denied(Capability.TOOL_ADD)
        if denied:
            return denied
        if isinstance(tool, str):
            box = self.toolbox()
            key = next((n for n in box if n.lower() == tool.strip().lower()), None)
            if key is None:
                existing = self.session.tool_controller.find(tool)
                if existing is not None and existing.name.lower() == tool.strip().lower():
                    return self.session.add_tool(existing, pane=pane, at_front=at_front, focus=focus)
                return {"ok": False, "error": f"no tool called {tool!r} can be added",
                        "available": sorted(box)}
            tool = box[key]
        res = self.session.add_tool(tool, pane=pane, at_front=at_front, focus=focus, by=self.name)
        _log_agent_action(self.session_state, "add_tool", str(res.get("tool")))
        return res

    def remove_tool(self, name: str) -> dict:
        """Remove a tool that was added during the session. Needs ``tool_add``."""
        return self._denied(Capability.TOOL_ADD) or self.session.remove_tool(name, by=self.name)

    def _find_tool(self, name: str):
        sess = self.session
        t = sess.tool_controller.find(name)
        available = getattr(sess, "tool_available", lambda _t: True)
        if t is None or not available(t):
            return None, {"ok": False, "error": f"no tool named {name!r}",
                          "tools": [x.name for x in sess.tools if available(x)]}
        if getattr(sess, "tool_private_to_human", lambda _t: False)(t):
            return None, {"ok": False, "error": f"{t.name} shows the participant's own information, which you cannot "
                                                "see in this negotiation. Ask the participant about it instead "
                                                "(get_private_information tells you what only you know)."}
        st = self.session.tool_state(t)
        if not st["enabled"] and not t.permanent and self.session.admin_prefs.get("allow_tool_switch", True):
            return None, {"ok": False, "error": f"{t.name} is switched off; turn it on first (set_tool_enabled)",
                          "help": t.help_text()}
        return t, None

    def read_tool(self, name: str, max_chars: int = 4000) -> dict:
        """What a tool currently shows, as text (``{"ok", "tool", "text"}``),
        including its inputs and buttons. Needs ``tool_use``."""
        denied = self._denied(Capability.TOOL_USE)
        if denied:
            return denied
        t, err = self._find_tool(name)
        if err:
            return err
        with self._as_assistant():
            text = t.describe_for_agent(max_chars=max_chars)
        return {"ok": True, "tool": t.name, "text": text}

    def _as_assistant(self):
        """Render tools as the Assistant sees them (see ``NegotiationSession.viewing_as``)."""
        fn = getattr(self.session, "viewing_as", None)
        return fn("assistant") if fn is not None else contextlib.nullcontext()

    # ------------------------------------------------------------------ #
    # What only the Assistant knows (hani2.information)                    #
    # ------------------------------------------------------------------ #
    def private_information(self) -> dict:
        """What only the Assistant knows in this negotiation and who holds what
        (``{"ok", "who_holds_what", ...}``): its part of the participant's
        preferences, the value on disagreement when it has it, the past
        negotiations it holds and the market research. Needs ``private_info``.

        Python Assistants can read ``self.session.human_ufun`` directly; use this
        helper instead to keep to the information split of the study."""
        denied = self._denied(Capability.PRIVATE_INFO)
        if denied:
            return denied
        from hani2.information import private_view

        return {"ok": True, **self.run_on_doc(lambda: private_view(self.session))}

    def past_negotiation(self, pid: str) -> dict:
        """One past negotiation the Assistant holds, offer by offer
        (``{"ok", "negotiation"}``). Needs ``private_info``."""
        denied = self._denied(Capability.PRIVATE_INFO)
        if denied:
            return denied
        from hani2.information import past_view

        st = self.session.information
        rec = st.past_by_id(pid)
        if rec is None or rec["id"] not in st.assistant_past:
            held = list(st.assistant_past)
            if rec is not None and rec["id"] in st.human_past:
                return {"ok": False, "error": f"{rec['id']} is held by the participant; ask them about it",
                        "you_hold": held}
            return {"ok": False, "error": f"no past negotiation {pid!r} among yours", "you_hold": held}
        return {"ok": True, "negotiation": self.run_on_doc(lambda: past_view(self.session, rec, who="assistant", max_offers=60))}

    def _executable_capabilities(self) -> set[str]:
        caps = set()
        for c in self.capabilities.effective():
            if c in (Capability.SUBMIT_COUNTER, Capability.ACCEPT, Capability.END) and \
                    not self.capabilities.autonomy_allows_execute(c):
                continue
            caps.add(c.value)
        return caps

    #: How long :meth:`use_tool` waits for a tool working in the background
    #: (one with a true ``busy`` attribute, such as an :class:`~hani2.tools.LLMTool`).
    tool_wait: float = 60.0

    def _wait_while_busy(self, tool) -> None:
        import time

        deadline = time.monotonic() + max(0.0, float(self.tool_wait or 0))
        time.sleep(0.05)
        while getattr(tool, "busy", False) and time.monotonic() < deadline:
            time.sleep(0.2)

    def use_tool(self, name: str, *, inputs: dict[str, Any] | None = None, action: str | None = None,
                 payload: dict[str, Any] | None = None, row: int | None = None) -> dict:
        """Operate a tool like the participant would: set its ``inputs`` (by
        input name), then press the button ``action`` (or select table ``row``
        of the table whose selection action is ``action``). Anything the tool
        then does to the offer, message, accept or end obeys the agent's own
        capabilities and autonomy. Returns what the tool shows afterwards,
        once a tool working in the background (an LLM tool) is done or
        :attr:`tool_wait` seconds have passed. Needs ``tool_use``."""
        denied = self._denied(Capability.TOOL_USE)
        if denied:
            return denied
        t, err = self._find_tool(name)
        if err:
            return err
        from hani2.tools.describe import controls_of

        with t.view_lock, self._as_assistant():
            controls = controls_of(list(t.view() or []))
        for key in inputs or {}:
            if key not in controls["inputs"]:
                return {"ok": False, "error": f"{t.name} has no input {key!r}", "inputs": sorted(controls["inputs"])}
        sess = self.session
        results: list[Any] = []
        from hani2.naming import unlabel_value

        inputs = {k: _coerce_input(controls["inputs"][k], unlabel_value(v, sess.labels if hasattr(sess, "labels") else {}))
                  for k, v in (inputs or {}).items()}
        with sess.acting_for_agent(self._executable_capabilities()):
            for key, value in inputs.items():
                try:
                    t.on_input(key, value)
                except Exception as e:  # noqa: BLE001
                    return {"ok": False, "error": f"setting {key!r} failed: {e}"}
            if action is not None:
                if inputs:  # the new inputs may change the buttons and tables on offer
                    with t.view_lock, self._as_assistant():
                        controls = controls_of(list(t.view() or []))
                if action not in controls["actions"] and action not in controls["tables"]:
                    return {"ok": False, "error": f"{t.name} has no button or table action {action!r} now",
                            "actions": sorted(controls["actions"]) + sorted(controls["tables"]),
                            "text": self._describe(t)}
                if action in controls["actions"] and controls["actions"][action].get("disabled"):
                    label = controls["actions"][action].get("label") or action
                    return {"ok": False, "error": f"the {label} button is disabled now"}
                data = dict(controls["actions"].get(action, {}).get("payload") or {})
                data.update(payload or {})
                if action in controls["tables"]:
                    rows = controls["tables"][action].get("rows") or []
                    idx = int(row if row is not None else data.get("index", -1))
                    if not 0 <= idx < len(rows):
                        return {"ok": False, "error": f"row must be between 0 and {len(rows) - 1}"}
                    data.update(row=rows[idx], index=idx)
                try:
                    results.append(t.on_action(action, data))
                except Exception as e:  # noqa: BLE001
                    return {"ok": False, "error": f"{action!r} failed: {e}"}
        self._wait_while_busy(t)
        _log_agent_action(self.session_state, "use_tool", f"{t.name}:{action or ''}:{sorted(inputs or {})}")
        ev.log_event(sess.sid, ev.EventType.TOOL_INTERACTION, user=sess.user, component=t.name,
                     action=f"agent:{action or 'input'}", value={"inputs": inputs or {}, "row": row})
        return {"ok": True, "tool": t.name, "text": self._describe(t)}

    def _describe(self, t) -> str:
        with self._as_assistant():
            return t.describe_for_agent()

    # ------------------------------------------------------------------ #
    # Participant controls                                                 #
    # ------------------------------------------------------------------ #
    def set_user_enabled(self, on: bool) -> None:
        self.user_enabled = bool(on)
        self.session_state["support_agent_user_enabled"] = self.user_enabled

    def set_proactive_delivery(self, channel: str) -> None:
        if channel in _VALID_PROACTIVE_DELIVERY:
            self.user_proactive_delivery = channel
            self.session_state["support_proactive_delivery"] = channel

    def client_state(self) -> dict[str, Any]:
        caps = []
        for c in Capability:
            if c.value in ADMIN_ONLY_CAPABILITIES:  # decided by the admin; never shown to the participant
                continue
            label, desc = CAPABILITY_INFO.get(c.value, (c.value, ""))
            caps.append(dict(key=c.value, label=label, description=desc,
                             granted=bool(self.capabilities.admin_capabilities.get(c.value, False)),
                             on=self.capabilities.has(c)))
        return {
            "available": True,
            "name": self.name,
            "enabled": self.user_enabled,
            "busy": self.busy,
            "capabilities": caps,
            "autonomy": {"admin": self.capabilities.admin_autonomy.value,
                         "user": self.capabilities.user_autonomy.value,
                         "effective": self.capabilities.autonomy.value},
            "proactive_delivery": self.user_proactive_delivery,
            "autopilot": self.autopilot,
        }

    # ------------------------------------------------------------------ #
    # Entry points called by the session                                   #
    # ------------------------------------------------------------------ #
    def handle_user_message(self, text: str) -> None:
        """The human sent a chat message (runs in a worker thread)."""
        if not self.user_enabled:
            self.post("(The assistant is turned off. Switch it on to chat.)")
            return
        if self._answer_question(text):
            return
        self._run_turn(user_text=text, context_note=self._context_snapshot())

    def _context_snapshot(self) -> str | None:
        try:
            ctx = self.context()
        except Exception:
            return None
        return "[Current negotiation state]\n" + json.dumps(ctx, default=str, indent=2)

    def on_draft_changed(self, draft: dict[str, Any]) -> None:
        """The human edited the counter-offer. Default: the reserved-value warning."""
        self.warn_if_draft_below_reserved()

    def warn_if_draft_below_reserved(self) -> None:
        """Warn (once until fixed) when the draft is worth less than the reserved value."""
        if not self.user_enabled:
            return
        try:
            ctx = self.session.context("human")  # the warning is shown to the participant: only what they may know
        except Exception:
            return
        util, reserved = ctx.get("draft_offer_utility"), ctx.get("reserved_value")
        if util is None or reserved is None or not ctx.get("is_my_turn"):
            return
        if util >= reserved:
            if self._below_reserved_warned:
                self.session.annotate("offer", None)
            self._below_reserved_warned = False
            return
        if self._below_reserved_warned:
            return
        self._below_reserved_warned = True
        if self.capabilities.has(Capability.TOAST):
          self.session.toast(
            f"Your current offer is worth less than your reserved value ({util:.0%} < {reserved:.0%}). "
            "If it is accepted you would do worse than ending.",
            "warning",
            duration=12000,
            action={"label": "Discuss with the assistant", "kind": "open_assistant"},
            source="assistant",
          )
        if self.capabilities.has(Capability.ANNOTATE):
            self.session.annotate("offer", f"Worth {util:.0%} — below your reserved value ({reserved:.0%})", "warning")
        self.show_on_board(
            f"⚠️ **Recommendation:** your draft offer ({util:.0%}) is below your reserved value "
            f"({reserved:.0%}). Consider a stronger offer or ending."
        )

    _ACTION_TOOLS = {"submit_counter_offer", "accept_offer", "end_negotiation"}

    def on_event(self, event_name: str, nmi=None) -> None:
        """A negotiation lifecycle event: ``negotiation_started``,
        ``action_requested`` or ``negotiation_ended``."""
        if event_name == "action_requested":
            self._below_reserved_warned = False
        if not self.user_enabled:
            return
        proactive = self.settings.get("proactive", {}) or {}
        if not proactive.get(f"on_{event_name}", False):
            return
        if self._busy.locked():
            return
        note = self.proactive_note(event_name)
        if note:
            channel = self.user_proactive_delivery if self.user_proactive_delivery in _VALID_PROACTIVE_DELIVERY else "toast"
            self._run_turn(system_note=note, context_note=self._context_snapshot(), output_channel=channel)

    def proactive_note(self, event_name: str) -> str | None:
        """The system note that seeds a proactive turn (``None`` = stay silent)."""
        if event_name == "negotiation_started":
            return "(system) A new negotiation just started. Briefly greet the human and offer help if appropriate."
        if event_name == "action_requested":
            return ("(system) It is now the human's turn to act. If you have a useful observation about the "
                    "opponent's latest offer, share it concisely.")
        if event_name == "negotiation_ended":
            return "(system) The negotiation ended. Give a one-sentence debrief."
        return None

    def on_panel_action(self, panel_id: str, action: str, payload: dict[str, Any]) -> None:
        """A button in one of your panels was clicked. Default: tell the LLM."""
        if not self.user_enabled:
            return
        self._run_turn(system_note=f"(panel {panel_id}) clicked {action}"
                       + (f" with {json.dumps(payload, default=str)}" if payload else ""),
                       context_note=self._context_snapshot())

    # ------------------------------------------------------------------ #
    # Autopilot                                                            #
    # ------------------------------------------------------------------ #
    def set_autopilot(self, active: bool) -> None:
        if active and not self.autopilot:
            self._saved_autonomy = (self.capabilities.admin_autonomy, self.capabilities.user_autonomy)
            self.capabilities.admin_autonomy = Autonomy.FULL
            self.capabilities.user_autonomy = Autonomy.FULL
            self._autopilot_stalls = 0
        elif not active and self.autopilot and self._saved_autonomy:
            self.capabilities.admin_autonomy, self.capabilities.user_autonomy = self._saved_autonomy
            self._saved_autonomy = None
        self.autopilot = bool(active)

    def autopilot_step(self, delay: float = 0.0) -> None:
        """Called by the session on every human turn while this agent drives the
        autopilot. Waits for a previous turn to finish (skipping a turn would
        stall the round), then decides."""
        import time as _time

        if delay > 0:
            _time.sleep(delay)
        deadline = _time.time() + 60
        while self._busy.locked() and _time.time() < deadline:
            _time.sleep(0.02)
        if self.autopilot and self.session.is_my_turn():
            self._run_autopilot_turn()

    def _run_autopilot_turn(self) -> None:
        note = ("(system) AUTOPILOT is engaged: it is your turn and NO human is watching. You MUST act now by "
                "calling exactly one of submit_counter_offer, accept_offer, or end_negotiation.")
        acted: set[str] = set()
        try:
            acted = self._run_turn(system_note=note, context_note=self._context_snapshot(), force_action=True) or set()
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            print(f"[autopilot] Assistant turn failed: {e}")
        if acted & self._ACTION_TOOLS:
            self._autopilot_stalls = 0
            return
        self._autopilot_stalls += 1
        self._autopilot_fallback()

    def _autopilot_fallback(self) -> None:
        if self._autopilot_stalls >= 3:
            self.toast("Autopilot disengaged: the Assistant kept failing to act. You're back in control.", "error")
            self.session.set_autopilot(False)
            return
        self.toast("Autopilot: the agent didn't act; sending a counter-offer to keep the negotiation moving.", "warning")
        try:
            res = self.session.send_counter()
            if isinstance(res, dict) and not res.get("ok"):
                print(f"[autopilot] fallback counter-offer refused: {res.get('error')}")
        except Exception as e:  # noqa: BLE001
            print(f"[autopilot] fallback failed: {e}")

    # ------------------------------------------------------------------ #
    # The tool-calling loop                                                #
    # ------------------------------------------------------------------ #
    def _deliver_assistant_message(self, text: str, *, channel: str = "chat") -> None:
        if not text:
            return
        if channel == "toast":
            self.toast(text, "info")
        elif channel == "board":
            self.show_on_board(text)
        else:
            self.post(text)

    def _set_busy_state(self) -> None:
        try:
            self.session.push_state()
        except Exception:
            pass

    def _run_turn(self, user_text: str | None = None, system_note: str | None = None,
                  context_note: str | None = None, force_action: bool = False,
                  output_channel: str = "chat") -> set[str]:
        executed: set[str] = set()
        if not self._busy.acquire(blocking=False):
            if not force_action:
                self.post("(I'm still working on the previous request — one moment.)")
            return executed
        self._set_busy_state()
        try:
            if user_text is not None:
                content = f"{context_note}\n\n---\n{user_text}" if context_note else user_text
                self.messages.append({"role": "user", "content": content})
            if system_note is not None:
                if context_note and user_text is None:
                    system_note = f"{context_note}\n\n---\n{system_note}"
                self.messages.append({"role": "user", "content": system_note})
            tools = self.dispatcher.schemas()
            max_iter = int(self.settings.get("max_tool_iterations", 10))
            if self._harness_turn(tools, executed, output_channel, force_action=force_action):
                return executed
            for _ in range(max_iter):
                message = self._complete(tools, force_action=force_action and not executed)
                self.messages.append(message)
                tool_calls = message.get("tool_calls") or []
                if not tool_calls:
                    if message.get("content"):
                        self._deliver_assistant_message(message["content"], channel=output_channel)
                    return executed
                for tc in tool_calls:
                    executed.add(self._execute_tool_call(tc))
                if force_action and executed & self._ACTION_TOOLS:
                    return executed
            if not force_action:
                self._final_answer(output_channel)
            return executed
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            if not force_action:
                from hani2.connections import llm_error

                self.post(f"⚠️ Assistant error: {llm_error(e, admin=self.session.is_admin)}")
            return executed
        finally:
            self._busy.release()
            self._set_busy_state()

    def model(self):
        """The language model this Assistant uses (a :class:`hani2.model_chain.Resolution`): the
        ``assistant`` chain's first available entry, chosen once per session."""
        from hani2 import model_chain

        models = model_chain.models_of(self.session_state)
        return models.get("assistant") if models is not None else model_chain.resolve("assistant")

    def _own_model(self, res):
        """When no model chain is set (``res`` comes from the old settings files) but this
        Assistant's own settings (a group file, ``make_session(assistant_settings=...)``) name a
        different provider/model, that model (one entry, unchecked)."""
        from hani2 import model_chain

        s = self.settings or {}
        if not res.implicit or not (s.get("provider") or s.get("model")):
            return None
        if res.entry is not None and str(s.get("model")) == res.model and \
                str(s.get("provider") or "").lower() in (res.entry.provider, res.provider):
            return None
        entries = model_chain.legacy_entries(s, "assistant", "assistant")
        if not entries:
            return None
        return model_chain.resolve("assistant", chain=entries,
                                   source=model_chain.Source("assistant settings", {}, implicit=True))

    def _final_answer(self, output_channel: str) -> None:
        """The tool loop ran out of rounds: ask once more, with tools switched off, for an answer
        from what the tools returned so far; a short apology only if that fails too."""
        self.messages.append({"role": "user", "content": (
            "(system) You have used all your tool calls for this request. Answer the human now in a few "
            "sentences, from what you already found. Do not call any tool.")})
        text = ""
        try:
            message = self._complete(self.dispatcher.schemas(), no_tools=True)
            if not message.get("tool_calls"):
                text = str(message.get("content") or "").strip()
                if text:
                    self.messages.append({"role": "assistant", "content": text})
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        self._deliver_assistant_message(
            text or "Sorry, I could not finish working that out. Could you ask me again, perhaps more simply?",
            channel=output_channel)

    def _complete(self, tools: list[dict], force_action: bool = False, no_tools: bool = False) -> dict:
        """One LLM completion via litellm; returns ``{"role", "content", "tool_calls"?}``.

        The model comes from the ``assistant`` model chain (see :mod:`hani2.model_chain`); a hard
        failure moves the session to the next available entry."""
        from hani2 import model_chain

        s = self.settings
        models = model_chain.models_of(self.session_state)
        used: list = []

        def _messages(res):
            used[:] = [res]
            return flatten_tool_messages(self.messages) if res.is_ollama else self.messages

        extra: dict[str, Any] = {}
        if tools:
            # with no_tools the schemas stay (the history holds tool calls) but none may be called
            extra["tools"] = tools
            extra["tool_choice"] = "none" if no_tools else "required" if force_action else "auto"
        # the session's own settings may still tune the call (old keys; a chain entry's params win)
        params = {k: s.get(k) for k in ("temperature", "max_tokens") if s.get(k) is not None}
        from hani2.recording.recorder import current_actor, llm_role

        with llm_role("autopilot" if current_actor() == "autopilot" else "support"):
            res0 = models.get("assistant") if models is not None else model_chain.resolve("assistant")
            own = self._own_model(res0)
            if own is not None:  # this Assistant's own settings name a model and no chain is set
                res0, models = own, None
            params = {k: v for k, v in params.items() if k not in (res0.entry.params if res0.entry else {})}
            response = model_chain.completion("assistant", _messages, models=models,
                                              resolution=None if models is not None else res0, params=params, **extra)
        msg = response.choices[0].message
        out: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls and used and used[0].is_ollama:
            parsed = parse_text_tool_calls(out["content"])
            if parsed:
                out["content"] = ""
                out["tool_calls"] = parsed
                return out
        if tool_calls:
            out["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                for tc in tool_calls
            ]
        return out

    def _harness_turn(self, tools: list[dict], executed: set[str], output_channel: str = "chat",
                      force_action: bool = False) -> bool:
        """When the ``assistant`` entry is an agent harness (see :mod:`hani2.harness`), run the whole
        turn through it: every HANI2 function it calls is executed here, by this Assistant's
        dispatcher (capabilities, events and recordings apply), and appended to the conversation as
        an ordinary tool call and result. Returns ``False`` when the entry is not a harness (or a
        hard failure moved the session to an entry that is not), so the usual loop runs instead."""
        import time as _time

        from hani2 import harness, model_chain
        from hani2.recording.recorder import current_actor, llm_role, record_llm_call

        models = model_chain.models_of(self.session_state)
        res = models.get("assistant") if models is not None else model_chain.resolve("assistant")
        own = self._own_model(res)
        if own is not None:
            res, models = own, None
        n = 0

        def execute(name: str, args: dict) -> Any:
            nonlocal n
            if force_action and executed & self._ACTION_TOOLS:
                # the autopilot's turn ends with its first action (as in the usual loop)
                return {"ok": False, "error": "this turn already acted; stop now"}
            n += 1
            call_id = f"harness-{n}"
            self.messages.append({"role": "assistant", "content": "", "tool_calls": [
                {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})
            try:
                result = self.dispatcher.execute(name, args)
            except Exception as e:  # noqa: BLE001
                result = {"ok": False, "error": str(e)}
            executed.add(_executed_name(name, result))
            self.messages.append({"role": "tool", "tool_call_id": call_id, "name": name,
                                  "content": json.dumps(result, default=str)})
            return result

        params = {k: self.settings.get(k) for k in ("max_tokens",) if self.settings.get(k) is not None}
        while res.ok and res.is_harness:
            assert res.connection is not None
            sent = list(self.messages)
            t0 = _time.perf_counter()
            kw = {"model": f"{harness.LITELLM_PROVIDER}/{res.model}", "messages": sent, "tools": tools}
            with llm_role("autopilot" if current_actor() == "autopilot" else "support"):
                try:
                    reply = harness.run_tools(res.connection, res.model, sent, tools, execute,
                                              {**params, **(res.entry.params if res.entry else {})})
                except Exception as e:  # noqa: BLE001
                    from hani2.connections import redact

                    reason = redact(f"{type(e).__name__}: {e}")[:300]
                    record_llm_call(kw, None, _time.perf_counter() - t0, reason)
                    if n or not model_chain.hard_failure(e) or models is None:
                        raise  # functions already ran: do not repeat the turn on another model
                    res = models.advance("assistant", reason, failed=res)
                    if not res.ok:
                        raise
                    continue
                record_llm_call(kw, _harness_response(reply), _time.perf_counter() - t0)
            self.messages.append({"role": "assistant", "content": reply.text or ""})
            if reply.text:
                self._deliver_assistant_message(reply.text, channel=output_channel)
            return True
        return False

    def _execute_tool_call(self, tc: dict) -> str:
        name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        try:
            result = self.dispatcher.execute(name, args)
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "error": str(e)}
        self.messages.append({"role": "tool", "tool_call_id": tc.get("id", name), "name": name,
                              "content": json.dumps(result, default=str)})
        return _executed_name(name, result)


def _executed_name(name: str, result: Any) -> str:
    """How a call counts in a turn's ``executed`` set: a failed or refused action
    (``ok`` false) is not an action, so the autopilot's stall net still catches it."""
    return name if not isinstance(result, dict) or result.get("ok", True) else f"{name}:failed"


def _harness_response(reply: Any) -> Any:
    """A harness reply in the shape the recorder reads (``choices[0].message``, ``usage``)."""
    from types import SimpleNamespace

    u = reply.usage or {}
    usage = SimpleNamespace(prompt_tokens=int(u.get("input_tokens", 0)), completion_tokens=int(u.get("output_tokens", 0)),
                            total_tokens=int(u.get("input_tokens", 0)) + int(u.get("output_tokens", 0)))
    calls = [SimpleNamespace(function=SimpleNamespace(name=c.name, arguments=json.dumps(c.arguments, default=str)))
             for c in reply.calls]
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply.text, tool_calls=calls or None))],
                           usage=usage, _hidden_params={"response_cost": reply.cost_usd})


def _coerce_input(component: dict, value: Any) -> Any:
    """Give a value from a language model the type the input expects
    (``"80"`` → ``80.0`` for a slider, ``"true"`` → ``True`` for a checkbox,
    an option's label → its value)."""
    t = component.get("type")
    try:
        if t in ("slider", "number") and isinstance(value, str):
            return float(value)
        if t in ("checkbox", "switch") and isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        if t in ("select", "radio") and component.get("options"):
            opts = component["options"]
            if not any(o.get("value") == value for o in opts):
                for o in opts:
                    if str(o.get("value")) == str(value) or str(o.get("label")) == str(value):
                        return o.get("value")
    except (TypeError, ValueError):
        pass
    return value


def load_class(path: str) -> type:
    """Load ``module:Class``, ``module.Class`` or ``path/to/file.py:Class``."""
    if ":" in path:
        mod, _, attr = path.rpartition(":")
    else:
        mod, _, attr = path.rpartition(".")
    if mod.endswith(".py"):
        from importlib import util as import_util
        from pathlib import Path

        file = Path(mod).expanduser().resolve()
        if not file.is_file():
            raise FileNotFoundError(file)
        name = f"hani2_user_{file.stem}_{abs(hash(str(file)))}"
        module = sys.modules.get(name)
        if module is None:
            spec = import_util.spec_from_file_location(name, file)
            module = import_util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        return getattr(module, attr)
    return getattr(importlib.import_module(mod), attr)


#: the Assistant's class (``SupportAgent`` is its old name; both are the same object)
Assistant = SupportAgent


def resolve_agent_class(settings: dict) -> type[SupportAgent]:
    """Resolve ``agent_class`` (``module:Class``, ``module.Class`` or
    ``path/to/file.py:Class``); fall back to :class:`SupportAgent` (with a
    warning) if it cannot be loaded.

    Kept for scripts that call it; sessions no longer use it: they load the
    class strictly (:func:`load_assistant_class`) and fail loudly."""
    path = (settings.get("agent_class") or "").strip()
    if not path:
        return SupportAgent
    try:
        klass = load_class(path)
        if not (isinstance(klass, type) and issubclass(klass, SupportAgent)):
            raise TypeError(f"{path} is not an Assistant (SupportAgent) subclass")
        return klass
    except Exception as e:  # noqa: BLE001
        print(f"[hani2] WARNING: could not load custom agent_class {path!r} ({e}); using the default agent")
        return SupportAgent


class AssistantLoadError(RuntimeError):
    """An assigned Assistant could not be imported or created."""


def load_assistant_class(spec: str) -> type[SupportAgent]:
    """Load an Assistant class strictly (raises :class:`AssistantLoadError`)."""
    try:
        klass = load_class(spec)
    except Exception as e:  # noqa: BLE001
        raise AssistantLoadError(f"cannot import the Assistant {spec!r}: {type(e).__name__}: {e}") from e
    if not (isinstance(klass, type) and issubclass(klass, SupportAgent)):
        raise AssistantLoadError(f"{spec!r} is not an Assistant (SupportAgent) subclass")
    return klass


_SOURCES = {"settings": "agent_class in assistant_settings.json", "env": "--assistant / HANI2_ASSISTANT_CLASS "
             "or --assistants / HANI2_ASSISTANTS", "study": "assistants in study.yaml / project.yaml",
             "schedule": "schedule.json", "group": "the group file", "query": "the page URL"}


def _where(choice: Any) -> str:
    src = _SOURCES.get(getattr(choice, "source", ""), "")
    return f" (from {src})" if src else ""


def _assistant_failed(session: "NegotiationSession", choice: Any, message: str) -> None:
    """Fail loudly: no Assistant, a visible error for the participant and admins, an event and a log line."""
    print(f"[hani2] ERROR: {message}")
    session.assistant_error = message
    session.ss["support_agent"] = None
    try:
        ev.log_event(session.sid, ev.EventType.ERROR, user=session.user, component="assistant",
                     action="assistant_failed", value={"error": message, **(choice.to_dict() if choice else {})})
    except Exception:  # pragma: no cover
        pass
    try:
        session.toast(f"The Assistant could not be started: {message}", "error", duration=0)
    except Exception:  # pragma: no cover
        pass


def create_support_agent_for(session: "NegotiationSession", choice: Any = None,
                             settings: dict | None = None) -> SupportAgent | None:
    """Create the session's Assistant.

    The class comes from the session's Assistant pool (see :mod:`hani2.assignment`):
    an Assistant (URL, group file, schedule.json, ``--assistants``, study.yaml /
    project.yaml, or ``agent_class`` in assistant_settings.json) that cannot be
    imported or created leaves the session without an Assistant and shows the error
    (a banner, a toast, an ``ERROR`` event, the ``assistant_error`` column); there is
    no silent fallback to the built-in Assistant."""
    from hani2 import assignment

    settings = settings or getattr(session, "assistant_settings", None) or load_support_agent_settings()
    assert settings is not None
    session.assistant_settings = settings
    session.assistant_error = None
    if not support_agent_enabled(settings, is_admin=session.is_admin):
        session.assistant_choice = None
        session.ss["support_agent"] = None
        return None
    if choice is None:
        try:
            choice = assignment.choose_assistant(session, settings, getattr(session, "round_plan", None))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            choice = assignment.AssistantChoice(spec=None, source="error", error=f"could not assign an Assistant: {e}")
    session.assistant_choice = choice
    if choice.error or not choice.spec:
        _assistant_failed(session, choice, choice.error or "no Assistant to run")
        return None
    if assignment.is_no_assistant(choice.spec):
        # the no-Assistant control arm: assigned like any Assistant, runs none
        session.ss["support_agent"] = None
        return None
    if choice.source == "group":
        # a group file naming an Assistant is there to try that Assistant: start it switched on
        session.ss["support_agent_default_enabled"] = True
    session.ss.pop("assistant_presentation_override", None)  # a new Assistant decides afresh
    try:
        klass = load_assistant_class(choice.spec)
        agent = klass(session.ss, settings)
    except AssistantLoadError as e:
        _assistant_failed(session, choice, str(e) + _where(choice))
        return None
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _assistant_failed(session, choice, f"the Assistant {choice.spec!r} failed to start: "
                                           f"{type(e).__name__}: {e}{_where(choice)}")
        return None
    session.ss["support_agent"] = agent
    return agent


def get_or_create_support_agent(session_state: dict[str, Any], settings: dict | None = None) -> SupportAgent | None:
    agent = session_state.get("support_agent")
    if agent is None:
        agent = create_support_agent_for(session_state["_session"])
    return agent


#: new name of :func:`create_support_agent_for`
create_assistant_for = create_support_agent_for
