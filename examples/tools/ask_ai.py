"""Step 5 - an LLM tool with its own input: ask any question about the deal.

``controls_view`` adds a text area above the button and ``build_prompt``
decides what the model sees: here the question, the participant's
preferences and the transcript.
"""

from hani2.tools import LLMTool, ui


class AskAI(LLMTool):
    name = "Ask the AI"
    description = "Ask a language model any question about this negotiation."
    help = """
    **What it does.** Answers your own question about the negotiation, for example
    "Is the opponent's last offer good for me?" or "Which issue should I give up first?".

    **How it works.** Your question, your preferences (issue weights and option values) and
    the offers so far are sent to the language model when you press **Ask**. The answer is
    shown here and is never sent to your opponent. The model can be wrong: check its advice
    against the Preferences tool.
    """
    icon = "message-circle-question"
    button_label = "Ask"
    empty_text = "Type a question and press Ask."
    prompt = "Answer the Participant's question in at most five sentences."

    def controls_view(self):
        return [ui.textarea("question", self.values.get("question", ""), rows=2,
                            placeholder="e.g. Which issue matters most to my opponent?")]

    def check(self):
        if not (self.values.get("question") or "").strip():
            return "Type a question first."

    def build_prompt(self):
        return "\n\n".join([
            self.prompt,
            "Question: " + self.values["question"].strip(),
            "The Participant's preferences:\n" + self.session.llm_context().get_ufun_description(),
            self.context_text(),  # the issues and the offers so far
        ])
