"""The :class:`LLMTool` base class: a tool that asks the language model.

Subclass it, write a ``prompt`` and you have a working tool: a button sends the
prompt (with the negotiation so far) to the configured model in the background,
and the reply is shown as Markdown::

    from hani2.tools import LLMTool

    class Summary(LLMTool):
        name = "Summary"
        description = "Summarise the negotiation so far."
        prompt = "Summarise this negotiation in three bullet points."

Override :meth:`LLMTool.build_prompt` to choose what the model sees,
:meth:`LLMTool.check` to refuse to run (e.g. while an input is empty),
:meth:`LLMTool.controls_view` to add inputs above the button and
:meth:`LLMTool.answer_view` to show the reply differently.
"""

from __future__ import annotations

from typing import Any

from hani2.tools import ui
from hani2.tools.base import Tool

__all__ = ["LLMTool"]


class LLMTool(Tool):
    """A tool with one button that asks the language model and shows the reply.

    Class attributes, on top of those of :class:`Tool`:

    ==================== =====================================================
    ``prompt``           The instructions for the model (required).
    ``system``           Optional extra instructions put before the prompt.
    ``include_transcript`` Add the negotiation so far to the prompt (default
                         True).
    ``max_turns``        How many of the latest offers the transcript keeps.
    ``button_label``     The button's text.
    ``empty_text``       Shown before the first answer.
    ``needs_offers``     Disable the button until at least one offer exists.
    ==================== =====================================================
    """

    icon = "sparkles"
    pane = "side"
    timing = "start"
    prompt: str = ""
    system: str | None = None
    include_transcript: bool = True
    max_turns: int = 40
    button_label: str = "Ask the AI"
    busy_label: str = "Thinking..."
    empty_text: str = "Press the button to ask the language model."
    needs_offers: bool = False

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        #: The last reply (after :meth:`postprocess`), or ``None``.
        self.answer: str | None = None
        #: The last error message, or ``None``.
        self.error: str | None = None
        #: True while the model is working.
        self.busy = False
        self._answered_at = 0

    # -- what to ask -----------------------------------------------------------
    def build_prompt(self) -> str:
        """The text sent to the model. Default: ``prompt`` followed by
        :meth:`context_text`."""
        return "\n\n".join(p for p in (self.prompt.strip(), self.context_text()) if p)

    def context_text(self) -> str:
        """The issues and (with ``include_transcript``) the offers so far, as text."""
        parts = []
        if self.issues:
            lines = []
            for i in self.issues:
                vals = (", ".join(str(v) for v in i.all) if i.is_discrete() and i.cardinality <= 20
                        else f"{i.min_value} to {i.max_value}")
                lines.append(f"- {i.name}: {vals}")
            parts.append("Issues under negotiation:\n" + "\n".join(lines))
        if self.include_transcript:
            parts.append("Negotiation so far (oldest first):\n" + (self.transcript(self.max_turns) or "(no offers yet)"))
        return "\n\n".join(p for p in parts if p)

    def check(self) -> str | None:
        """Called when the button is pressed; return an error message to stop
        before asking the model (for example when an input is empty)."""
        return None

    def postprocess(self, reply: str) -> str:
        """Turn the model's raw reply into the text to show. Default: unchanged."""
        return reply

    # -- what to show ----------------------------------------------------------
    def controls_view(self) -> list[ui.Component]:
        """Components shown above the button (inputs the prompt can read from
        ``self.values``). Default: none."""
        return []

    def answer_view(self, answer: str) -> list[ui.Component]:
        """How the reply is shown. Default: as Markdown in a card."""
        return [ui.card(ui.markdown(answer, size="sm"))]

    def can_run(self) -> bool:
        if self.busy:
            return False
        return not self.needs_offers or bool(self.trace())

    def view(self) -> list[ui.Component]:
        from hani2.llm_service import get_llm_status

        comps: list[ui.Component] = []
        st = get_llm_status("tools")
        if not st.get("configured"):
            comps.append(ui.alert(f"No language model is configured (provider `{st.get('provider')}`).", "warning"))
        comps += self.controls_view()
        comps.append(ui.button(self.busy_label if self.busy else self.button_label, "ask", variant="primary",
                               icon="sparkles", disabled=not self.can_run(), full=True))
        if self.error:
            comps.append(ui.alert(self.error, "error"))
        if self.answer:
            comps += self.answer_view(self.answer)
            new = len(self.trace()) - self._answered_at
            if new > 0:
                comps.append(ui.text_block(f"{new} new offer{'s' if new > 1 else ''} since this answer.", muted=True))
        elif not self.busy and not self.error:
            comps.append(ui.text_block(self.empty_text, muted=True))
        return comps

    # -- running ---------------------------------------------------------------
    def run(self) -> None:
        """Ask the model in the background (what the button does)."""
        if self.busy:
            return
        problem = self.check()
        if problem:
            self.error = problem
            self.refresh()
            return
        self.busy, self.error = True, None
        self.refresh()
        self.session.submit(self._run)

    def _run(self) -> None:
        try:
            n = len(self.trace())
            reply = self.ask_llm(self.build_prompt(), system=self.system)
            self.answer = self.postprocess(reply)
            self._answered_at = n
        except Exception as e:  # noqa: BLE001 - shown in the browser, redacted
            from hani2.connections import llm_error

            self.error = llm_error(e, admin=getattr(self.session, "is_admin", False))
        finally:
            self.busy = False
            self.refresh()

    def on_input(self, name: str, value: Any) -> None:
        self.values[name] = value
        if not isinstance(value, str):  # no redraw on every key press
            self.refresh()

    def on_action(self, action: str, payload: dict[str, Any]) -> None:
        if action == "ask":
            self.values.update(payload or {})  # the current input values ride along with the click
            self.run()

    def negotiation_started(self, session_state, nmi) -> None:
        self.answer, self.error, self._answered_at = None, None, 0
        super().negotiation_started(session_state, nmi)
