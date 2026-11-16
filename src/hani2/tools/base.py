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

Register it in ``settings/env.json``::

    {"tools": {"extra": ["my_package.tools:OfferCounter"]}}

or ship it in a package with an entry point in the ``hani2.tools`` group.
"""

from __future__ import annotations

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
    ``description`` One line shown in the tool picker / to the support agent.
    ``icon``        A lucide icon name (kebab case), e.g. ``"chart-line"``.
    ``pane``        Default pane: ``"upper"``, ``"lower"`` or ``"side"``.
    ``timing``      When the tool appears: ``"always"`` (page open),
                    ``"load"`` (scenario loaded), ``"start"`` (negotiation
                    started) or ``"end"`` (negotiation finished).
    ``permanent``   Always on: no enable switch, cannot be hidden.
    ``admin_only``  Only admins (or ``?admin=1`` sessions) get the tool.
    ``guest``       Whether guests / playground users get it (default True).
    ``enabled``     Default state of the user-facing enable switch. Disabled
                    tools still show their tab, but :meth:`view` is not called
                    until the user switches them on.
    ``order``       Sort key inside its pane (smaller first).
    ============== ===========================================================
    """

    name: str = ""
    description: str = ""
    icon: str = "wrench"
    pane: str = "upper"
    timing: str = "start"
    permanent: bool = False
    admin_only: bool = False
    guest: bool = True
    enabled: bool = True
    order: int = 100

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

    def trace(self) -> list:
        """The mechanism's ``full_trace`` (empty before the negotiation starts)."""
        m = self.mechanism
        try:
            return list(m.full_trace) if m is not None else []
        except Exception:
            return []

    def context(self) -> dict[str, Any]:
        """The live negotiation snapshot (same dict the support agent sees)."""
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

    def render(self) -> list[ui.Component]:
        """Called by HANI2; wraps :meth:`view` with error reporting."""
        self._dirty = False
        try:
            return list(self.view() or [])
        except Exception as e:  # noqa: BLE001 - a broken tool must not break the page
            import traceback

            traceback.print_exc()
            return [ui.alert(f"`{self.name}` failed to render: {e}", "error")]


class OutcomeSelector(Tool):
    """A tool that proposes an outcome and fills the offer with it.

    Override :meth:`get_outcome`; a **Set Offer** button is appended to
    :meth:`selector_view` automatically.
    """

    pane = "side"
    icon = "wand-sparkles"
    button_label = "Set Offer"

    def get_outcome(self) -> Outcome | None:
        s = self.scenario
        return s.outcome_space.random_outcome() if s is not None else None  # type: ignore

    def selector_view(self) -> list[ui.Component]:
        return []

    def can_set(self) -> bool:
        return bool(self.session_state.get("negotiation_running"))

    def view(self) -> list[ui.Component]:
        return [
            *self.selector_view(),
            ui.button(
                self.button_label,
                "set_offer",
                variant="primary",
                icon="arrow-left-to-line",
                disabled=not self.can_set(),
                full=True,
            ),
        ]

    def set_outcome(self) -> dict:
        return self.set_offer(self.get_outcome())

    def on_action(self, action: str, payload: dict[str, Any]) -> None:
        if action == "set_offer":
            r = self.set_outcome()
            if not r.get("ok", True):
                self.toast(r.get("error", "Could not set the offer"), "warning")
