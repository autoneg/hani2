"""Walkthrough video: negotiating with an Assistant, advanced (docs/walkthroughs/hi-advanced.md).

    uv run --with kokoro-onnx==0.6.1 --with numpy --with playwright \
        python scripts/videos/film_hi_advanced.py [--show]

A HANI2 server with the built-in Assistant (the local default language model, qwen3:4b-instruct
on Ollama) that also shares an estimate of the opponent, opening in the tool area
(``presentation.place: tools``); participants may choose the scenario and the opponent. The
Assistant's answers come from the model, so they differ from take to take.
"""

from __future__ import annotations

import hv
from hv import ASSISTANT_PANEL, COUNTER, NEC, SEND, START, tab

NAME = "hani2-walkthrough-hi-advanced"
W = "w"
ASSISTANT = f"{hv.ROOT / 'scripts' / 'screenshots' / 'docs_assistant.py'}:LLMDocsAssistant"
ENV = {"negotiation": {"n_steps": 20, "time_limit": None},
       "playground": {"choices": {"scenario": True,
                                  "opponent": ["LinearTBNegotiator", "BoulwareTBNegotiator", "ConcederTBNegotiator"]}}}
HEADER_ASSISTANT = "header button:has-text('Assistant')"
BY_OPPONENT = "select:has(option:has-text('estimated utility'))"

N = {
    "intro": "This is the advanced walkthrough for negotiating with an Assistant. We choose our own scenario "
          "and opponent, decide how much the Assistant may do, use its estimate of what the opponent wants, "
          "and see the Assistant take the place of the tools.",
    "recap": "A reminder: utility is what a deal is worth to you, the value on disagreement is what you get "
          "without a deal, and the deadline is when the negotiation ends.",
    "choose": "When the study allows it, pickers appear before the start. Here you may choose the scenario and "
           "the opponent.",
    "opp": "Assigned automatically keeps the study's choice. We pick one of the AI opponents instead. A choice "
        "holds for one negotiation only.",
    "start": "Now we start.",
    "place": "In this study the Assistant opens in the tool area, in place of the open tool.",
    "settings": "The sliders button opens the Assistant's settings.",
    "levels": "How much may the Assistant do? Suggest: it fills offers and points at buttons, and you act. Semi: "
           "it sends offers, but asks before it accepts or ends. Full: it acts on its own.",
    "abilities": "Below, a switch for each ability, and where its unprompted messages appear. You can give it "
              "less than the study allows, never more.",
    "ask": "Concrete questions get the best answers. Let us ask what the opponent cares about.",
    "estimate": "The Assistant can also share an estimate: a guess of the opponent's preferences, made from its "
             "role and its offers.",
    "close": "Closing the Assistant brings back the same tool, as it was.",
    "plot": "With an estimate, the Negotiation Plot appears. Each dot is a possible deal: what it is worth to you "
         "across, and what the opponent probably gets, up.",
    "frontier": "The dashed line joins the deals where neither side can gain without the other losing. Good deals "
             "for both lie near it. The yellow banner says this is an estimate, and it may be wrong.",
    "selector": "The Utility-based Selector can use the estimate too. It can choose deals by the opponent's "
             "estimated value: still good for you, and more likely to be accepted.",
    "pick": "We take the deal at the top, check it, and send it.",
    "tips": "When you play people, the same Assistant helps you. Keep your messages friendly, and be patient: "
         "people need time to decide.",
    "bye": "That is the end of the walkthroughs. Thank you for watching, and good luck.",
}


def main() -> None:
    f = hv.film(NAME)
    hv.prewarm(f, hv.narration(globals()))
    with hv.server(["--assistant", ASSISTANT], env_json=ENV, opponent="LinearTBNegotiator",
                   assistant={"autonomy": "suggest", "presentation": {"place": "tools"}}) as url:
        with f:
            f.mark("Introduction")
            f.card("HANI2 walkthrough", "Negotiating with an Assistant", "Advanced: choices, autonomy and estimates",
                   ["Choose your opponent", "Autonomy", "Opponent estimate", "Assistant in the tools"])
            f.say(N["intro"], tail=0.5)
            f.say(N["recap"], tail=0.6)
            f.card_off()

            f.mark("Choose the scenario and the opponent")
            f.part("1 · YOUR CHOICES", NEC["teal"])
            hv.pane(f, W, url + "/play", sub="With an Assistant")
            hv.wait_for(f, W, START)
            f.say(N["choose"], caption="Pickers before the start", kicker="Your choices", wait=False)
            f.point(W, "[data-testid=choice-pickers]", hold=3.0)
            f.finish_speech(); f.unring()
            f.say(N["opp"], caption="Opponent: assigned automatically, or your pick", kicker="Your choices", wait=False)
            f.point(W, "select[aria-label='Opponent']", hold=1.5)
            f.frame(W).locator("select[aria-label='Opponent']").select_option(index=2)
            f.sleep(1.5)
            f.finish_speech(); f.unring()
            f.say(N["start"], wait=False)
            f.click(W, START)
            hv.my_turn(f, W)
            f.finish_speech()

            f.mark("How much may the Assistant do")
            f.part("2 · AUTONOMY", NEC["bright"])
            f.say(N["place"], caption="The Assistant in the tool area", kicker="Where it appears", wait=False)
            f.click(W, HEADER_ASSISTANT)
            hv.wait_for(f, W, ASSISTANT_PANEL)
            f.finish_speech()
            f.say(N["settings"], wait=False)
            f.click(W, "button[aria-label='Assistant settings']")
            f.finish_speech()
            f.say(N["levels"], caption="Suggest · Semi · Full", kicker="Autonomy", wait=False)
            f.point(W, "text=How much may the assistant do?", hold=1.0)
            for level in ("Suggest", "Semi", "Full"):
                f.point(W, f"[role=dialog] :text-is('{level}')", hold=2.5)
            f.finish_speech(); f.unring()
            f.say(N["abilities"], caption="Abilities: switch off what you do not want", kicker="Autonomy", wait=False)
            f.point(W, "text=Abilities", hold=3.0)
            f.finish_speech(); f.unring()
            f.frame(W).locator("[role=dialog]").last.press("Escape")
            f.sleep(0.8)

            f.mark("Ask better questions")
            f.say(N["ask"], caption="Ask concrete questions", kicker="Assistant", wait=False)
            hv.ask(f, W, "What do you think my opponent, the landlord, cares about most?")
            f.finish_speech()
            f.say(N["estimate"], caption="An estimate of the opponent", kicker="Estimate")

            f.mark("The opponent estimate")
            f.part("3 · THE ESTIMATE", NEC["orange"])
            f.say(N["close"], wait=False)
            f.click(W, "button[aria-label='Close assistant']")
            f.finish_speech()
            f.click(W, tab("Negotiation Plot"))
            f.sleep(1.5)
            f.say(N["plot"], caption="Negotiation Plot: worth to you, and to the opponent", kicker="Estimate", wait=False)
            f.point(W, "text=Estimate", hold=1.5)
            f.point(W, ".js-plotly-plot, svg.main-svg", hold=3.0)
            f.finish_speech(); f.unring()
            f.say(N["frontier"], caption="Near the dashed line: good for both", kicker="Estimate")
            f.click(W, tab("Utility-based Selector"))
            f.sleep(1.0)
            f.say(N["selector"], caption="Choose deals by the opponent's estimated value", kicker="Estimate", wait=False)
            f.point(W, BY_OPPONENT, hold=1.5)
            f.frame(W).locator(BY_OPPONENT).first.select_option(label="The opponent's estimated utility")
            f.sleep(2.0)
            f.finish_speech(); f.unring()
            f.say(N["pick"], wait=False)
            f.click(W, "button:has-text('Set Offer')")
            f.sleep(1.0)
            if not f.loc(W, SEND).count():
                f.click(W, COUNTER)  # the selector filled the offer; open the editor to check it
            f.click(W, SEND)
            hv.my_turn(f, W)
            f.finish_speech()

            f.mark("Playing people")
            f.caption(None)
            f.part("")
            f.panes([])
            f.tiles("Playing people", [
                {"n": "1", "t": "Waiting", "d": "Play an AI instead is always offered", "color": NEC["bright"]},
                {"n": "2", "t": "Both start", "d": "The negotiation starts when both press Start", "color": NEC["teal"]},
                {"n": "3", "t": "Messages", "d": "Short and friendly: the other side is a person", "color": NEC["orange"]},
                {"n": "4", "t": "Leaving", "d": "Ends the negotiation without agreement", "color": NEC["magenta"]},
            ], kicker="Tips", cols=2)
            f.say(N["tips"], tail=0.6)
            f.tiles_off()
            f.card("HANI2 walkthrough", "Thank you", "The four walkthroughs are in the HANI2 documentation", [])
            f.say(N["bye"], tail=1.2)
        hv.finish(f, NAME)


if __name__ == "__main__":
    main()
