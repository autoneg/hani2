"""Level 11 - give the participant the interface they ask for (no LLM).

The agent offers a panel of choices when the negotiation starts and also
understands a few words in the chat. It switches between the full, simple and
bare (no tools) views, rewrites how offers read, makes the text bigger and
restyles the page. ``reset`` puts everything back to the scenario's defaults.
"""

from hani2.support_agent.runtime import SupportAgent
from hani2.tools import ui

#: A calmer colour scheme: the CSS colour variables are space-separated RGB values.
CALM_CSS = """
:root { --you: 32 110 120; --opponent: 150 100 170; --paper: 247 245 240; }
[data-region=header] { border-bottom-width: 2px; }
"""

CHOICES = [
    ("Everything", "full"),
    ("Simple", "simple"),
    ("No tools", "bare"),
    ("Offers as sentences", "sentences"),
    ("Bigger text", "bigger"),
    ("Calm colours", "calm"),
    ("Reset", "reset"),
]

#: Words in a chat message and the choice they mean; the first match wins, so "reset" comes first.
WORDS = {
    "reset": "reset", "default": "reset",
    "everything": "full", "full": "full", "all tools": "full",
    "simple": "simple", "simpler": "simple",
    "no tools": "bare", "bare": "bare", "hide the tools": "bare",
    "sentence": "sentences",
    "bigger": "bigger", "larger": "bigger",
    "calm": "calm", "colour": "calm", "color": "calm",
}


class InterfaceAgent(SupportAgent):
    def on_event(self, event_name: str, nmi=None) -> None:
        if self.user_enabled and event_name == "negotiation_started":
            self.show_panel(
                "screen",
                "How should your screen look?",
                [
                    ui.markdown("Pick one, or just tell me (for example *no tools* or *bigger text*)."),
                    ui.row(*[ui.button(label, action) for label, action in CHOICES]),
                ],
            )

    def on_panel_action(self, panel_id: str, action: str, payload: dict) -> None:
        if panel_id == "screen":
            self.message_user(self.apply(action), channel="toast")

    def handle_user_message(self, text: str) -> None:
        low = text.lower()
        choice = next((c for w, c in WORDS.items() if w in low), None)
        if choice is None:
            self.post("Tell me what you would like: everything, simple, no tools, sentences, bigger text, "
                      "calm colours or reset.")
            return
        self.post(self.apply(choice))

    def apply(self, choice: str) -> str:
        """Carry out one choice and say what happened."""
        if choice in ("full", "simple", "bare"):
            res = self.set_layout(view=choice)
            done = {"full": "Showing every tool.", "simple": "One tools column now.",
                    "bare": "Tools hidden: just the offers and me."}[choice]
        elif choice == "sentences":
            names = [i["name"] for i in self.context()["issues"]]
            # e.g. "Quantity 6, Price 200" -> "6 for Quantity and 200 for Price"
            template = " and ".join("{%s} for %s" % (n, n) for n in names)
            res = self.set_offer_display(offer_template=template, offer_display="text")
            done = "Offers now read as sentences."
        elif choice == "bigger":
            res = self.set_interface(prefs={"font_scale": 1.25})
            done = "Bigger text."
        elif choice == "calm":
            res = self.set_interface(custom_css=CALM_CSS)
            done = "Calmer colours."
        else:  # reset
            self.set_offer_display(reset=True)
            self.set_interface(prefs={"font_scale": 1.0}, custom_css="")
            res = self.set_layout(view="full")
            done = "Back to the defaults."
        if not res.get("ok"):
            return f"I could not do that: {res.get('error') or res.get('refused')}"
        return done
