"""Level 9 - reshape the interface and build your own panel (no LLM).

When the negotiation starts the agent switches to the calm *focus* layout and
shows a panel asking how the participant wants to work. Its buttons call
``on_panel_action``. On every turn the panel lists the three offers the partner
made that are best for the participant, each with a button that copies it into
the counter-offer.
"""

from hani2.support_agent.runtime import SupportAgent
from hani2.tools import ui


class PanelAgent(SupportAgent):
    def on_event(self, event_name: str, nmi=None) -> None:
        if not self.user_enabled:
            return
        if event_name == "negotiation_started":
            self.set_layout(view="focus")
            self.show_panel(
                "welcome",
                "How do you want to work?",
                [
                    ui.markdown("I hid the analysis tools so you can focus on the offers."),
                    ui.row(
                        ui.button("Keep it simple", "simple", variant="primary"),
                        ui.button("Show me everything", "full"),
                    ),
                ],
            )
        elif event_name == "action_requested":
            self.show_best_offers()

    def show_best_offers(self) -> None:
        ctx = self.context()
        offers = [h for h in ctx["history"] if h["by"] == "partner" and h["offer"]]
        best = sorted(offers, key=lambda h: h["utility"] or 0, reverse=True)[:3]
        if not best:
            return
        rows = [ui.outcome(h["offer"], h["utility"]) for h in best]
        buttons = [ui.button(f"Use offer {i + 1}", "use", payload={"offer": h["offer"]}) for i, h in enumerate(best)]
        self.show_panel(
            "best",
            "Partner's best offers for you",
            [*rows, ui.row(*buttons)],
            placement="side",
        )

    def on_panel_action(self, panel_id: str, action: str, payload: dict) -> None:
        if panel_id == "welcome":
            self.set_layout(view="simple" if action == "simple" else "full")
            if action == "full":
                self.focus_tool("Utility Plot")
            self.close_panel("welcome")
            self.message_user("Done. Ask me if you want the layout changed again.", channel="toast")
        elif panel_id == "best" and action == "use":
            self.session_state["actions"]["set_offer"](payload["offer"])
            self.highlight("send", "Review the offer, then send it.")
