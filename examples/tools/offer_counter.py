"""Step 1 - the smallest useful tool: a few numbers about the negotiation."""

from hani2.tools import Tool, ui


class OfferCounter(Tool):
    name = "Offer Counter"
    description = "How many offers each side made so far."
    icon = "hash"
    pane = "side"

    def view(self):
        trace = self.trace()
        me = self.session_state.get("human_id")
        mine = sum(1 for row in trace if row[3] == me)
        return [
            ui.stats(
                ui.stat("Your offers", mine),
                ui.stat("Partner offers", len(trace) - mine),
            )
        ]
