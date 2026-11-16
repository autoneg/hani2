"""Step 2 - an interactive tool: try a deal before you offer it.

Inputs are bound by ``name``; ``self.values`` holds what the user picked.
The button fills the counter-offer with the chosen outcome.
"""

from hani2.tools import Tool, ui


class WhatIf(Tool):
    name = "What If"
    description = "Pick a value for every issue and see what the deal is worth to you."
    icon = "flask-conical"
    pane = "side"
    timing = "load"

    def view(self):
        if self.human_ufun is None:
            return [ui.text_block("Load a scenario first.", muted=True)]
        inputs, outcome = [], []
        for issue in self.issues:
            options = list(issue.all) if issue.is_discrete() else [issue.min_value, issue.max_value]
            value = self.values.get(issue.name, options[0])
            outcome.append(value)
            inputs.append(ui.select(issue.name, options, value, label=issue.name))
        utility = float(self.human_ufun(tuple(outcome)))
        reserved = float(self.human_ufun.reserved_value)
        verdict = ("success", "Better than no deal") if utility >= reserved else ("error", "Worse than no deal")
        return [
            ui.grid(*inputs, cols=2),
            ui.stat("Worth to you", f"{utility:.0%}", hint=verdict[1], kind=verdict[0]),
            ui.button("Use as my offer", "use", variant="primary", icon="arrow-left-to-line",
                      disabled=not self.session_state.get("negotiation_running")),
        ]

    def on_action(self, action, payload):
        if action == "use":
            self.set_offer({i.name: self.values.get(i.name) for i in self.issues if i.name in self.values})
            self.toast("Copied into your offer", "success")
