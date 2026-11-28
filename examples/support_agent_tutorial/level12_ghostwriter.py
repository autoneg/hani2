"""Level 12 - answer the interface's AI features yourself.

When the participant presses **Write message** or **Offer from message**, or sends an offer with no
message (or a message with no offer) in a study that writes or reads them automatically, the
interface asks the Assistant first. The default Assistant answers with the study's own prompts on
its own model. This one writes messages from a template and reads "Issue: value" offers itself,
with no language model, and passes anything else on to the default.
"""

import re

from hani2.support_agent.runtime import SupportAgent


class GhostwriterAgent(SupportAgent):
    def write_message(self, offer, wait=15.0):
        """The message that goes with ``offer`` ({issue: value})."""
        if not offer:
            return {"text": None, "error": "Fill every issue first."}
        terms = ", ".join(f"{issue} {value}" for issue, value in offer.items())
        ctx = self.session.context("assistant")
        if ctx.get("partner_offer"):
            text = f"Thanks for your offer. I can do {terms}. I think that is fair for both of us."
        else:
            text = f"Hello! To get us started, I propose {terms}."
        return {"text": text, "error": None}

    def offer_from_message(self, text, wait=15.0):
        """The offer in the participant's message, when it names every issue as "Issue: value"."""
        found = {}
        for issue in self.session.issues:
            m = re.search(rf"{re.escape(issue.name)}\s*[:=]\s*([\w.\-]+)", text or "", re.IGNORECASE)
            if m:
                found[issue.name] = m.group(1)
        if len(found) == len(self.session.issues) and self.session.offer_outcome(found) is not None:
            return {"outcome": found, "error": None}
        # not in that form: the default reads it with the study's prompt on this Assistant's model
        # (and returns None, so the interface asks its own model, when there is none)
        return super().offer_from_message(text, wait)
