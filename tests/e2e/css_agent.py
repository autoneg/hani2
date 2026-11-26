"""A rule-based Assistant for the style-sheet browser test: "hide" tries a sheet that hides
Accept (the page must drop it), "calm" applies a harmless one."""

from hani2.support_agent.runtime import SupportAgent


class CssAgent(SupportAgent):
    def handle_user_message(self, text: str) -> None:
        if "hide" in text:
            res = self.set_interface(custom_css="[data-anchor=accept] { visibility: hidden; }")
        else:
            res = self.set_interface(custom_css=":root { --paper: 10 200 30; }")
        self.post("done" if res.get("ok") else f"refused {res}")
