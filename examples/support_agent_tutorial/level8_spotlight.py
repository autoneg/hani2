"""Level 8 - point at the interface: highlights and notes (no LLM).

On every turn the agent reads the negotiation, then
* annotates each issue the partner just moved on ("Partner conceded here"),
* spotlights the button it recommends, with a one-line reason.
"""

from hani2.support_agent.runtime import SupportAgent


class SpotlightAgent(SupportAgent):
    def __init__(self, session_state, settings):
        super().__init__(session_state, settings)
        self._last_partner_offer = None

    def on_event(self, event_name: str, nmi=None) -> None:
        if not self.user_enabled or event_name != "action_requested":
            return
        ctx = self.context()
        offer = ctx["partner_offer"]
        if offer is None:
            return

        # 1. Notes on the issues the partner changed since its last offer.
        previous = self._last_partner_offer or {}
        for issue, value in offer.items():
            if issue in previous and previous[issue] != value:
                self.annotate(f"issue:{issue}", f"Partner moved: {previous[issue]} → {value}", kind="tip")
            else:
                self.annotate(f"issue:{issue}", None)  # remove an old note
        self._last_partner_offer = offer

        # 2. Spotlight the recommended button.
        utility, reserved = ctx["partner_offer_utility"], ctx["reserved_value"]
        if utility < reserved:
            self.highlight("reject", "Worse than no deal. Make a counter-offer.")
        elif utility >= max(reserved, 0.9 - 0.4 * (ctx["relative_time"] or 0)):
            self.highlight("accept", f"Worth {utility:.0%} to you. Consider accepting.", style="glow")
        else:
            self.highlight("partner_offer", "Acceptable but improvable. Counter a little higher.")
