"""How the Trade sample shows offers (see "Showing offers" in the scenario guide).

Every method is optional: drop one and HANI2 uses its default view.
"""

from hani2.display import OfferContext, OfferDisplay
from hani2.tools import ui


class TradeDisplay(OfferDisplay):
    # the default control of each issue, unless controls() draws its own
    widgets = {"Quantity": "slider"}

    def text(self, offer, ctx: OfferContext) -> str:
        """One line: toasts, the result, the Assistant, the history in text mode."""
        if offer is None:
            return super().text(offer, ctx)
        return f"{offer['Quantity']} items at {offer['Price']}$"

    def _deal(self, offer, ctx: OfferContext):
        q, p = offer["Quantity"], offer["Price"]
        return [ui.markdown(f"**{q}** items × **{p}$** = **{q * p:,}$**")]

    def history(self, offer, ctx: OfferContext):
        """The offer in a history bubble."""
        return self._deal(offer, ctx)

    def on_table(self, offer, ctx: OfferContext):
        """The opponent's current offer."""
        return self._deal(offer, ctx)

    def controls(self, draft, ctx: OfferContext):
        """The counter-offer editor: the default fields plus a running total and
        a button that meets the opponent halfway on the price."""
        q, p = draft.get("Quantity"), draft.get("Price")
        total = f"{q * p:,}$" if q is not None and p is not None else "—"
        return [
            ui.grid(ui.issue("Quantity"), ui.issue("Price", widget="buttons"), cols=2),
            ui.row(ui.badge(f"Total: {total}", "primary"),
                   ui.button("Meet halfway on price", action="halfway", icon="split"), align="center"),
        ]

    def on_action(self, action, payload, draft, ctx: OfferContext):
        """A button in controls() was clicked: return the issue values to set."""
        if action != "halfway" or not ctx.opponent_offer:
            return None
        prices = sorted(next(i for i in ctx.issues if i.name == "Price").all)
        mine, theirs = draft.get("Price") or prices[0], ctx.opponent_offer["Price"]
        middle = (mine + theirs) / 2
        return {"Price": min(prices, key=lambda v: abs(v - middle))}
