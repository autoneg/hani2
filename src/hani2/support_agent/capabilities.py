"""Capabilities and autonomy for the Assistant.

Two layers gate what the agent may do:

* the **admin grant** — the ceiling, configured in the settings;
* the **user preferences** — the human negotiator may switch capabilities off
  and lower the autonomy level, but can never go beyond the admin grant.

The *effective* capability set is the intersection, and the effective autonomy
is the lower of the two levels. Only effective capabilities are ever offered to
the agent's language model as callable functions.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["Capability", "Autonomy", "CapabilityState", "CAPABILITY_INFO", "ADMIN_ONLY_CAPABILITIES"]


class Capability(str, Enum):
    """Individually grantable abilities. ``value`` matches the settings keys."""

    CHAT = "chat"
    TOAST = "toast"
    PIN = "pin"
    TOOL_ENABLE = "tool_enable"
    TOOL_VISIBILITY = "tool_visibility"
    TOOL_ORDER = "tool_order"
    FILL_OFFER = "fill_offer"
    FILL_TEXT = "fill_text"
    SUBMIT_COUNTER = "submit_counter"
    ACCEPT = "accept"
    END = "end"
    HIGHLIGHT = "highlight"
    ANNOTATE = "annotate"
    LAYOUT = "layout"
    PRESENTATION = "presentation"
    PANELS = "panels"
    OFFER_DISPLAY = "offer_display"
    INTERFACE = "interface"
    TOOL_ADD = "tool_add"
    TOOL_USE = "tool_use"
    LLM_TOOL = "llm_tool"
    PRIVATE_INFO = "private_info"
    OPPONENT_MODEL = "opponent_model"
    OPPONENT_UTILITY = "opponent_utility"


#: Human-readable labels / descriptions (used by the settings screens).
CAPABILITY_INFO: dict[str, tuple[str, str]] = {
    "chat": ("Chat", "Talk with you in the assistant panel and ask you questions"),
    "toast": ("Notifications", "Pop up short notifications (you can read them all later in the notifications list)"),
    "pin": ("Pinned messages", "Pin messages above or below the negotiation; the screen makes room for them"),
    "tool_enable": ("Enable tools", "Switch analysis tools on or off"),
    "tool_visibility": ("Show / hide tools", "Show, hide and focus tool tabs"),
    "tool_order": ("Rearrange tools", "Reorder tools and move them between panes"),
    "fill_offer": ("Fill the offer", "Put values in your counter-offer fields"),
    "fill_text": ("Write the message", "Write the message to your opponent"),
    "submit_counter": ("Send counter-offers", "Send a counter-offer for you"),
    "accept": ("Accept", "Accept your opponent's offer"),
    "end": ("End", "End the negotiation"),
    "highlight": ("Highlight", "Spotlight parts of the interface with a short note"),
    "annotate": ("Annotate", "Attach notes to issues, offers and other elements"),
    "layout": ("Change the layout", "Switch between the full, simple, focus and bare (no tools) views, and resize or collapse regions"),
    "offer_display": ("Change how offers read", "Rewrite how offers are shown: the offer sentence, number formats, value names and the control of each issue"),
    "interface": ("Adjust the interface", "Change your display settings (text size, history, offer order) and restyle the page"),
    "presentation": ("Choose how it appears", "Appear as a panel, a character or both, open beside the page or over the tool area, and decide whether you can hide the character"),
    "panels": ("Custom panels", "Show interactive panels it builds (cards, tables, buttons)"),
    "tool_add": ("Add tools", "Add new tools to your screen while you negotiate, and remove the ones it added"),
    "tool_use": ("Use tools", "Read your tools and use their inputs and buttons"),
    "llm_tool": ("Answer the LLM tool", "Write the suggestions of the LLM offer tool itself, with what it knows of the "
                                        "negotiation and your conversation (otherwise the tool asks its own model)"),
    "private_info": ("Its own information", "Use what only it knows in this negotiation (past negotiations, market research, part of your preferences) to help you"),
    "opponent_model": ("Estimate the opponent", "Share its estimate of what the opponent wants; your Negotiation Plot and Utility-based Selector can then show it"),
    "opponent_utility": ("Know the opponent's preferences (oracle)",
                         "See the opponent's utility function and the opponent's utility of every offer — an "
                         "ablation (the information ceiling), off by default and never shown to the participant"),
}

#: capabilities only the admin grant decides: the participant neither sees nor switches them (an
#: experimental condition must not be self-selected or unblinded)
ADMIN_ONLY_CAPABILITIES: frozenset[str] = frozenset({"opponent_utility"})


class Autonomy(str, Enum):
    """How far the agent may act on negotiation decisions.

    SUGGEST — fill fields / highlight the recommended button; never execute an
              irreversible action.
    SEMI    — send counter-offers itself; accept / end go through your
              confirmation dialog.
    FULL    — execute anything in the effective capability set.
    """

    SUGGEST = "suggest"
    SEMI = "semi"
    FULL = "full"

    @property
    def rank(self) -> int:
        return {"suggest": 0, "semi": 1, "full": 2}[self.value]

    @classmethod
    def coerce(cls, value: "Autonomy | str | None", default: "Autonomy") -> "Autonomy":
        if isinstance(value, Autonomy):
            return value
        if isinstance(value, str):
            try:
                return cls(value.lower())
            except ValueError:
                return default
        return default


class CapabilityState:
    """Resolves the effective capabilities/autonomy from admin grant ∩ user prefs."""

    def __init__(
        self,
        admin_capabilities: dict[str, bool],
        admin_autonomy: Autonomy | str,
        user_capabilities: dict[str, bool] | None = None,
        user_autonomy: Autonomy | str | None = None,
    ):
        self.admin_capabilities = dict(admin_capabilities)
        self.admin_autonomy = Autonomy.coerce(admin_autonomy, Autonomy.SUGGEST)
        self.user_capabilities = dict(user_capabilities) if user_capabilities is not None else dict(admin_capabilities)
        self.user_autonomy = Autonomy.coerce(user_autonomy, self.admin_autonomy)

    def has(self, capability: Capability | str) -> bool:
        """Effective = granted by the admin AND not switched off by the user."""
        key = capability.value if isinstance(capability, Capability) else capability
        if key in ADMIN_ONLY_CAPABILITIES:
            return bool(self.admin_capabilities.get(key, False))
        return bool(self.admin_capabilities.get(key, False)) and bool(self.user_capabilities.get(key, True))

    @property
    def autonomy(self) -> Autonomy:
        """The lower (more restrictive) of the admin and user levels."""
        return self.admin_autonomy if self.admin_autonomy.rank <= self.user_autonomy.rank else self.user_autonomy

    def set_user_capability(self, capability: Capability | str, on: bool) -> None:
        key = capability.value if isinstance(capability, Capability) else capability
        if key in ADMIN_ONLY_CAPABILITIES:
            return
        self.user_capabilities[key] = bool(on)

    def set_user_autonomy(self, autonomy: Autonomy | str) -> None:
        self.user_autonomy = Autonomy.coerce(autonomy, self.user_autonomy)

    def effective(self) -> set[Capability]:
        return {c for c in Capability if self.has(c)}

    def autonomy_allows_execute(self, capability: Capability) -> bool:
        a = self.autonomy
        if capability == Capability.SUBMIT_COUNTER:
            return a.rank >= Autonomy.SEMI.rank
        if capability in (Capability.ACCEPT, Capability.END):
            return a.rank >= Autonomy.FULL.rank
        return True

    def autonomy_allows_confirm(self, capability: Capability) -> bool:
        if capability in (Capability.ACCEPT, Capability.END):
            return self.autonomy.rank >= Autonomy.SEMI.rank
        return True
