"""Step 4 - a tool that uses a language model: summarise the negotiation.

``LLMTool`` does the work: a button, a background call to the configured
model, a busy state, errors and a Markdown answer. The tool only says what to
ask. By default the prompt is followed by the issues and the transcript of
the offers so far.
"""

from hani2.tools import LLMTool


class NegotiationSummary(LLMTool):
    name = "Summary"
    description = "An AI summary of the negotiation so far: positions, concessions and open issues."
    help = """
    **What it does.** Writes a short summary of the negotiation so far: where each side
    stands, who has conceded on what, which issues are still open and what to try next.

    **How it works.** When you press **Summarise**, the issues and every offer and message so
    far (with what each offer is worth to you) are sent to the language model, which writes
    the summary shown here. Nothing is sent to your opponent. Press the button again after
    new offers for a fresh summary.
    """
    icon = "notebook-pen"
    button_label = "Summarise"
    needs_offers = True
    empty_text = "Press Summarise once a few offers have been made."
    prompt = """You are helping a person (the Participant) who negotiates with an Opponent.
Summarise the negotiation below for the Participant in at most six short bullet points:
where each side stands, what each side has conceded, which issues are still open, and one
suggestion for the next move. Use plain language and do not invent offers."""
