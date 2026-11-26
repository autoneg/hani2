"""The :class:`Tool` base class.

A tool is a small Python object that lives for one browser session. It receives
the negotiation lifecycle callbacks and describes its UI
declaratively with :mod:`hani2.tools.ui` components. HANI2 renders the view in
one of three panes (``upper``, ``lower`` or ``side``), re-rendering it whenever
the tool calls :meth:`Tool.refresh` (which every lifecycle hook does by default).

Minimal tool::

    from hani2.tools import Tool, ui

    class OfferCounter(Tool):
        name = "Offer Counter"
        pane = "side"

        def view(self):
            n = len(self.trace())
            return [ui.stat("Offers so far", n)]

Register it by saving the file in the tools folder (``$HANI2_HOME/tools``,
see ``hani2 tools path``), by listing it in ``settings/env.json``::

    {"tools": {"extra": ["my_package.tools:OfferCounter"]}}

or by shipping it in a package with an entry point in the ``hani2.tools`` group.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from negmas import SAONMI, Outcome, Scenario
from negmas.sao import SAOResponse

from hani2.tools import ui

if TYPE_CHECKING:  # pragma: no cover
    from hani2.session import NegotiationSession

__all__ = ["Tool", "OutcomeSelector"]


class Tool:
    """Base class for all HANI2 tools.

    Class attributes (all optional) describe how the tool is registered:

    ============== ===========================================================
    ``name``        Tab title (defaults to the class name). Must be unique.
    ``description`` One line shown as the tab tooltip and to the Assistant.
    ``help``        Markdown explaining what the tool does and how it works.
                    Shown behind the tool's ``?`` button and given to the
                    Assistant. Falls back to ``description``.
    ``icon``        A lucide icon name (kebab case), e.g. ``"chart-line"``.
    ``pane``        Default pane: ``"upper"``, ``"lower"`` or ``"side"``.
    ``timing``      When the tool appears: ``"always"`` (page open),
                    ``"load"`` (scenario loaded), ``"start"`` (negotiation
                    started), ``"end"`` (negotiation finished) or ``"agent"``
                    (never on its own: only when the Assistant adds it).
    ``permanent``   Always on: no enable switch, cannot be hidden.
    ``admin_only``  Only logged-in administrators get the tool.
    ``guest``       Whether guests / playground users get it (default True).
    ``enabled``     Default state of the user-facing enable switch. Disabled
                    tools still show their tab, but :meth:`view` is not called
                    until the user switches them on.
    ``order``       Sort key inside its pane (smaller first).
    ``agent_hint``  Extra advice for the Assistant on when and how to use
                    the tool (added to what it reads with ``read_tool``).
    ``groups``      Tool groups the tool belongs to (e.g. ``("visualization",)``;
                    see :mod:`hani2.tool_groups`). ``admin`` (admin-only tools)
                    and ``assistant`` (timing ``"agent"``) are added for you.
    ``placement``   Where the tool goes in each view of the page (``full``,
                    ``simple``, ``focus``): ``{"simple": {"pane": "upper",
                    "visible": False, "order": 5}}``. A view (or key) not
                    given falls back to ``pane``, ``order`` and visible.
    ``needs_totals`` The tool shows what deals are worth to the human. It is
                    not offered in a round where the human knows only part of
                    their preferences (see :mod:`hani2.information`).
    ``private_information`` The tool shows information that is the human's
                    own (their preferences, their past negotiations). When the
                    human and the Assistant know different things, the
                    Assistant cannot read or use it.
    ============== ===========================================================

    Override :meth:`available` to offer a tool only in some rounds.

    The Assistant can read any tool (:meth:`describe_for_agent`) and use its
    inputs and buttons, so a tool written for people is usable by the agent
    without extra code.
    """

    name: str = ""
    description: str = ""
    help: str = ""
    icon: str = "wrench"
    pane: str = "upper"
    timing: str = "start"
    permanent: bool = False
    admin_only: bool = False
    guest: bool = True
    enabled: bool = True
    order: int = 100
    agent_hint: str = ""
    groups: tuple[str, ...] = ()
    placement: dict[str, dict[str, Any]] = {}
    needs_totals: bool = False
    private_information: bool = False

    def __init__(self, session_state: dict[str, Any], enabled: bool | None = None, **params: Any):
        self.session_state = session_state
        if enabled is not None:
            self.enabled = enabled
        if not self.name:
            self.name = type(self).__name__
        self.params = params
        #: Current values of this tool's inputs (``ui.select`` etc.), by name.
        self.values: dict[str, Any] = {}
        self._dirty = True

    # ------------------------------------------------------------------ #
    # Convenience accessors                                               #
    # ------------------------------------------------------------------ #
    @property
    def session(self) -> "NegotiationSession":
        return self.session_state["_session"]

    @property
    def scenario(self) -> Scenario | None:
        return self.session_state.get("scenario")

    @property
    def mechanism(self):
        return self.session_state.get("mechanism")

    @property
    def human_index(self) -> int:
        return int(self.session_state.get("human_index", 1))

    @property
    def human_ufun(self):
        return self.session_state.get("human_ufun")

    @property
    def agent_ufun(self):
        s = self.scenario
        if s is None:
            return None
        return s.ufuns[1 - self.human_index]

    @property
    def issues(self) -> list:
        s = self.scenario
        return list(s.outcome_space.issues) if s is not None else []  # type: ignore

    @property
    def is_admin(self) -> bool:
        return bool(self.session_state.get("is_admin", False))

    @property
    def may_see_opponent(self) -> bool:
        """Whether this participant may see the opponent's utilities: admins
        always; everyone when env.json → ``tools.show_opponent_utility`` is true."""
        if self.is_admin:
            return True
        from hani2.config import get_env

        return bool(get_env("tools.show_opponent_utility", False))

    def trace(self) -> list:
        """The mechanism's ``full_trace`` (empty before the negotiation starts)."""
        m = self.mechanism
        try:
            return list(m.full_trace) if m is not None else []
        except Exception:
            return []

    def available(self) -> bool:
        """Whether the tool is offered this round (hidden from the human and the
        Assistant otherwise). Default: always, except a ``needs_totals`` tool
        while the human may not see what deals are worth to them."""
        if not self.needs_totals:
            return True
        sess = self.session_state.get("_session")
        return sess is None or sess.sees_totals("human")

    def private_now(self) -> bool:
        """Whether the Assistant may not read or use this tool this round: a
        ``private_information`` tool, while the human and the Assistant know
        different things. Override to refine (e.g. private only when it shows
        something the Assistant does not know already)."""
        return self.private_information and self.information.split

    @property
    def information(self):
        """This round's :class:`~hani2.information.InformationState` (who knows what)."""
        from hani2.information import InformationState

        sess = self.session_state.get("_session")
        return getattr(sess, "information", None) or InformationState()

    def context(self) -> dict[str, Any]:
        """The live negotiation snapshot, with only what both the human and the
        Assistant may know (a tool is seen by the human and read by the Assistant)."""
        sess = self.session_state.get("_session")
        if sess is not None and hasattr(sess, "context"):
            return sess.context("shared")
        actions = self.session_state.get("actions") or {}
        fn = actions.get("context")
        return fn() if callable(fn) else {}

    def outcome_dict(self, outcome: Outcome | None) -> dict[str, Any] | None:
        if outcome is None:
            return None
        return {i.name: ui.jsonable(v) for i, v in zip(self.issues, outcome)}

    def set_offer(self, outcome: Outcome | dict[str, Any] | None) -> dict:
        """Fill the human's counter-offer draft (does not send it)."""
        if outcome is None:
            return {"ok": False, "error": "no outcome"}
        if not isinstance(outcome, dict):
            outcome = self.outcome_dict(tuple(outcome)) or {}
        return self.session_state["actions"]["set_offer"](outcome)

    def set_text(self, text: str) -> dict:
        return self.session_state["actions"]["set_text"](text)

    @classmethod
    def help_text(cls) -> str:
        """The tool's help (``help``, or ``description`` when it has none), dedented."""
        import inspect

        return inspect.cleandoc(cls.help or cls.description or "")

    def transcript(self, max_turns: int | None = None) -> str:
        """The negotiation so far as plain text, one line per offer or event.

        Each offer line says who made it, the offer, its utility for the
        participant and the message sent with it. Handy as input for an LLM.
        """
        hist = list(getattr(self.session, "history", []) or [])
        sees = getattr(self.session, "sees_totals", None)
        show_values = sees is None or bool(sees("shared"))  # the participant and the Assistant both read tools
        if max_turns:
            hist = hist[-max_turns:]
        lines = []
        for h in hist:
            if h.get("kind") == "system":
                lines.append(f"[{h.get('text', '')}]")
                continue
            who = "Participant" if h.get("by") == "human" else "Opponent"
            # explicit issue=value pairs: the display text ("I get everything.") reads like a quote to a model
            offer = ", ".join(f"{k}={v}" for k, v in (h.get("offer") or {}).items()) or h.get("offer_str") or "no offer"
            u = h.get("utility") if show_values else None
            line = f"{who}: {offer}" + (f" (worth {u:.0%} to the participant)" if isinstance(u, (int, float)) else "")
            if h.get("text"):
                line += f' - "{h["text"]}"'
            lines.append(line)
        return "\n".join(lines)

    def ask_llm(self, prompt: str, *, system: str | None = None, **settings: Any) -> str:
        """Send ``prompt`` to the configured language model and return its reply.

        Uses the session's ``tools`` model (the first available entry of the ``tools`` model
        chain, kept for the session; see :mod:`hani2.model_chain`); keyword arguments
        (``temperature``, ``max_tokens`` ...) tune the call, and ``provider`` / ``model`` call that
        model instead. Raises on failure. The call blocks, so make it from a
        background job (``self.session.submit``) or subclass :class:`LLMTool`.
        """
        from hani2.llm_service import complete

        return complete(prompt, system=system, session=getattr(self, "session", None), **settings)

    def describe_for_agent(self, max_chars: int = 4000) -> str:
        """What this tool shows, as text for the Assistant: its help text
        (:meth:`help_text`), :attr:`agent_hint`, and its current view (numbers, table rows, chart
        summaries, and the inputs and buttons it can use). Override to give
        the agent a better summary than the generic one."""
        from hani2.tools.describe import describe_components

        head = [f"Tool: {self.name}"]
        if self.help_text():
            head.append(self.help_text())
        if self.agent_hint:
            head.append(f"How to use it: {self.agent_hint}")
        try:
            with self.view_lock:
                comps = list(self.view() or [])
            relabel = getattr(self.session, "relabel", None)
            if relabel is not None:
                comps = relabel(comps)
            body = describe_components(comps, max_chars=max_chars)
        except Exception as e:  # noqa: BLE001
            body = f"(this tool could not be read: {e})"
        return "\n".join(head) + "\n\n" + (body or "(nothing to show yet)")

    def toast(self, message: str, level: str = "info") -> None:
        self.session.toast(message, level)

    def refresh(self) -> None:
        """Ask HANI2 to re-render this tool."""
        self._dirty = True
        try:
            self.session.tool_changed(self)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Lifecycle hooks                                                     #
    # ------------------------------------------------------------------ #
    def init(self, session_state: dict[str, Any]) -> None:
        """Called once when the tool is created."""

    def scenario_loaded(self, session_state: dict[str, Any], scenario: Scenario) -> None:
        """Called after a scenario is loaded."""
        self.refresh()

    def negotiation_started(self, session_state: dict[str, Any], nmi: SAONMI) -> None:
        """Called when the negotiation starts."""
        self.refresh()

    def negotiation_ended(self, session_state: dict[str, Any], nmi: SAONMI) -> None:
        """Called when the negotiation ends."""
        self.refresh()

    def action_requested(self, session_state: dict[str, Any], nmi: SAONMI) -> None:
        """Called whenever it becomes the human's turn."""
        self.refresh()

    def action_to_execute(self, session_state: dict[str, Any], nmi: SAONMI, action: SAOResponse) -> None:
        """Called just before the human's action is executed."""

    def action_executed(self, session_state: dict[str, Any], nmi: SAONMI, action: SAOResponse) -> None:
        """Called after the human's action is executed."""
        self.refresh()

    # ------------------------------------------------------------------ #
    # Rendering and interaction                                           #
    # ------------------------------------------------------------------ #
    def view(self) -> list[ui.Component]:
        """Return the tool's UI as a list of :mod:`hani2.tools.ui` components."""
        return [ui.text_block("This tool has no view.", muted=True)]

    def on_input(self, name: str, value: Any) -> None:
        """An input component changed. Default: store it and re-render."""
        self.values[name] = value
        self.refresh()

    def on_action(self, action: str, payload: dict[str, Any]) -> None:
        """A button was clicked or a table row selected."""

    @property
    def view_lock(self) -> threading.RLock:
        """Held while the tool is rendered or read by the Assistant, so the
        two never run :meth:`view` at the same time."""
        lock = self.__dict__.get("_view_lock")
        if lock is None:
            lock = self.__dict__.setdefault("_view_lock", threading.RLock())
        return lock

    def render(self) -> list[ui.Component]:
        """Called by HANI2; wraps :meth:`view` with error reporting."""
        self._dirty = False
        try:
            with self.view_lock:
                return list(self.view() or [])
        except Exception as e:  # noqa: BLE001 - a broken tool must not break the page
            import traceback

            traceback.print_exc()
            return [ui.alert(f"`{self.name}` failed to render: {e}", "error")]


class OutcomeSelector(Tool):
    """A tool that proposes an outcome and fills the offer with it.

    Override :meth:`get_outcome`; a **Set Offer** button (``button_label``) that fills the
    human's counter-offer with it is appended to :meth:`selector_view` automatically.

    A tool where picking a deal already fills the counter-offer (the Utility-based Selector,
    the Utility Bar) sets ``sends_offer = True`` and calls :meth:`pick` when a deal is picked;
    its button is then **Send offer** (``send_label``), which sends the picked deal as the
    human's offer, with the message they typed, exactly like the Send offer button under the
    counter-offer. It is disabled while the human cannot send; :meth:`send_blocker` gives the
    reason, shown as its tooltip.
    """

    pane = "side"
    icon = "wand-sparkles"
    groups = ("recommendation",)
    button_label = "Set Offer"
    #: True: picking a deal fills the counter-offer, and the button sends the picked deal
    sends_offer = False
    send_label = "Send offer"

    def get_outcome(self) -> Outcome | None:
        s = self.scenario
        return s.outcome_space.random_outcome() if s is not None else None  # type: ignore

    def selector_view(self) -> list[ui.Component]:
        return []

    def can_set(self) -> bool:
        return bool(self.session_state.get("negotiation_running"))

    # -- picking a deal and sending it (``sends_offer``) ------------------------------------
    def picked_outcome(self) -> dict[str, Any] | None:
        """The deal picked in the tool (issue name to value), or ``None``."""
        picked = self.values.get("picked")
        return dict(picked) if picked else None

    def pick(self, offer: dict[str, Any], index: int | None = None) -> dict:
        """Pick ``offer`` (row ``index`` of the tool's table): fill the counter-offer with it."""
        self.values["selected"] = index
        self.values["picked"] = None
        r = self.set_offer(offer)
        if r.get("ok", True):
            self.values["picked"] = dict(r.get("applied") or offer)
        else:
            self.values["selected"] = None
        self.refresh()
        return r

    def unpick(self) -> None:
        """Forget the picked deal (the counter-offer keeps it)."""
        self.values["selected"] = None
        self.values["picked"] = None

    def send_blocker(self) -> str | None:
        """Why the **Send offer** button cannot send now, or ``None`` when it can."""
        sess = self.session_state.get("_session")
        if not self.session_state.get("negotiation_running") or (sess is not None and sess.phase != "running"):
            return "The negotiation is not running."
        if sess is not None and getattr(sess, "autopilot_active", False):
            return "The autopilot is negotiating for you: take back control to send an offer."
        if sess is not None and (not sess.is_my_turn() or getattr(sess, "thinking", False)):
            return "Wait for your turn to send an offer."
        if sess is not None and sess.admin_prefs.get("text_only_mode"):
            return "Offers are sent as messages only here: use the message box."
        if self.picked_outcome() is None:
            return "Pick a deal first."
        return None

    def send_outcome(self) -> dict:
        """Send the picked deal as the human's offer, with the message they typed, as the
        Send offer button under the counter-offer does."""
        reason = self.send_blocker()
        if reason:
            return {"ok": False, "error": reason}
        offer = self.picked_outcome() or {}
        r = self.set_offer(offer)
        if not r.get("ok", True):
            return r
        res = self.session_state["actions"]["reject_counter"]() or {}
        if res.get("ok"):
            self.unpick()
            sess = self.session_state.get("_session")
            if sess is not None:
                sess.emit({"type": "draft_text", "text": ""})  # the message box empties, as after Send offer
            self.refresh()
        return res

    def draft_changed(self, session_state: dict[str, Any], draft: dict[str, Any]) -> None:
        """The counter-offer changed: a deal no longer in it is no longer picked."""
        picked = self.picked_outcome()
        if picked and any(draft.get(k) != v for k, v in picked.items()):
            self.unpick()
            self.refresh()

    def negotiation_started(self, session_state: dict[str, Any], nmi: SAONMI) -> None:
        self.unpick()
        super().negotiation_started(session_state, nmi)

    def view(self) -> list[ui.Component]:
        if self.sends_offer:
            reason = self.send_blocker()
            button = ui.button(self.send_label, "send_offer", variant="primary", icon="send", disabled=reason is not None,
                               full=True, tooltip=reason or "Send the picked deal as your offer, with your message")
        else:
            button = ui.button(self.button_label, "set_offer", variant="primary", icon="arrow-left-to-line",
                               disabled=not self.can_set(), full=True)
        return [*self.selector_view(), button]

    def set_outcome(self) -> dict:
        return self.set_offer(self.get_outcome())

    def on_action(self, action: str, payload: dict[str, Any]) -> Any:
        if action == "send_offer":
            r = self.send_outcome()
            if not r.get("ok", True):
                self.toast(r.get("error", "Could not send the offer"), "warning")
            return r
        if action == "set_offer":  # fill the counter-offer (still accepted from code and the Assistant)
            r = self.set_outcome()
            if not r.get("ok", True):
                self.toast(r.get("error", "Could not set the offer"), "warning")
            return r
        return None
