"""Level 10 - bring your own tool, and use the participant's tools (no LLM).

The agent ships a tool of its own, the *Deal Compass*. Its ``timing`` is
``"agent"``, so nobody sees it until the agent decides to add it: here, when the
negotiation starts. Then, every time it is the participant's turn, the agent
*uses* a tool the participant already has, the Utility-based Selector: it moves
the selector's minimum-utility slider just above the partner's offer and picks
the best row, which fills the counter-offer. The agent never needed to know how
the selector works inside: it reads the tool's inputs, buttons and table with
:meth:`read_tool` and operates them with :meth:`use_tool`, exactly like the
built-in LLM agent does with the ``read_tool`` / ``use_tool`` functions.

Capabilities used: ``tool_add`` (add the compass), ``tool_use`` (operate the
selector) and ``fill_offer`` (the selector fills the offer on the agent's
behalf, so the agent needs this too).
"""

from hani2.support_agent.runtime import SupportAgent
from hani2.tools import ui
from hani2.tools.base import Tool


class DealCompassTool(Tool):
    """How the offer on the table compares with your no-deal value, issue by issue."""

    name = "Deal Compass"
    description = "How the partner's offer compares with walking away, issue by issue."
    agent_hint = "Read it to see which issues of the partner's offer are weak for the participant."
    icon = "compass"
    pane = "side"
    timing = "agent"  # only the support agent adds it

    def view(self):
        offer = self.session.partner_offer()
        if offer is None or self.human_ufun is None:
            return [ui.text_block("Waiting for the partner's first offer.", muted=True)]
        u = float(self.human_ufun(offer))
        rv = float(self.human_ufun.reserved_value or 0)
        verdict = "better than walking away" if u > rv else "worse than walking away"
        rows = []
        values = getattr(self.human_ufun, "values", None)
        if values is not None:
            for issue, fun, v in zip(self.issues, values, offer):
                rows.append({"Issue": issue.name, "Partner offers": v, "Your score": float(fun(v))})
        out = [ui.stat("This offer is worth", f"{u:.0%}", hint=verdict, kind="good" if u > rv else "bad")]
        if rows:
            out.append(ui.table(rows, formats={"Your score": "percent"}))
        return out  # the base class re-renders the tool whenever it is the participant's turn


class ToolsmithAgent(SupportAgent):
    tools = [DealCompassTool]

    def on_event(self, event_name: str, nmi=None) -> None:
        if not self.user_enabled:
            return
        if event_name == "negotiation_started":
            res = self.add_tool("Deal Compass")
            if res.get("ok"):
                self.message_user("I added the Deal Compass beside your offer.", channel="toast")
        elif event_name == "action_requested":
            self.prepare_counter_offer()

    def prepare_counter_offer(self) -> None:
        offer = self.session.partner_offer()
        ufun = self.session_state.get("human_ufun")
        if offer is None or ufun is None:
            return
        # aim a little above what the partner offers now
        target = min(95, int(float(ufun(offer)) * 100) + 10)
        res = self.use_tool("Utility-based Selector", inputs={"min_util": target, "width": 15}, action="pick", row=0)
        if res.get("ok"):
            self.show_on_board(f"I filled your offer with the best option at {target}% or more. Check it, then send.")
