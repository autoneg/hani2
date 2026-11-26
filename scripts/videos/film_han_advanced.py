"""Walkthrough video: negotiating against an AI, advanced (docs/walkthroughs/han-advanced.md).

    uv run --with kokoro-onnx==0.6.1 --with numpy --with playwright \
        python scripts/videos/film_han_advanced.py [--show]

A fresh HANI2 server without an Assistant, the Apartment Lease scenario and a steadily conceding
AI opponent; the participant is the tenant.
"""

from __future__ import annotations

import hv
from hv import ACCEPT_ON, CONFIRM_ACCEPT, NEC, SEND, START, tab

NAME = "hani2-walkthrough-han-advanced"
W = "w"
ENV = {"negotiation": {"n_steps": 30, "time_limit": None}}
POPUP = "[data-testid=tool-popup]"

N = {
    "intro": "This is the advanced walkthrough for negotiating against an AI. You already know how to read "
          "an offer, make a counter-offer, accept and end. Now we look at the tools that find good offers "
          "for you, how to read your opponent, and how to make the page your own.",
    "recap": "A quick reminder. Utility is what a deal is worth to you, from zero to one hundred percent. The "
          "value on disagreement is what you get without a deal. And the deadline is the last round.",
    "start": "We start the negotiation, and wait for the opponent's first offer.",
    "ubar": "Picking one option per issue by hand is slow. The Utility Bar works the other way round: you say "
         "how much you want, and it finds the deals.",
    "ubar2": "The bar runs from zero percent on the left to one hundred percent on the right. The grey columns "
          "show how many possible deals lie at each value.",
    "marks": "The coloured lines mark your value on disagreement, the opponent's latest offer, and your own.",
    "drag": "Drag across the part of the bar you want. Here, deals worth between sixty and ninety percent to you.",
    "giveme": "Give me chooses how many deals you get. Ten deals give you a choice.",
    "pick": "Click a row, and the deal goes into your counter-offer. You can still change it before you send it.",
    "sent": "We send it. A good habit: start high, and move left slowly as the deadline comes closer. "
         "Never go below the no-deal line.",
    "menu": "The Tools menu, next to the Utility Bar, opens any tool in the same small window.",
    "hist": "The Value Histogram counts the options in the offers so far. An option the opponent never gives "
         "up probably matters to it. One it changes easily matters little: ask for more there.",
    "close": "We close the window, and the page is as it was.",
    "deadline": "Watch the deadline in the header. Many AI opponents concede more as it comes closer, but if it "
             "passes without a deal, you get only your value on disagreement.",
    "views": "The Layout button switches views. The simple view, the default, has one column of tools on the right.",
    "full": "The full view shows more tools at once: two panes on the left, and the offer tools next to the "
         "offer area.",
    "focus": "The focus view shows only the offers and the offer area. The Tools menu still opens any tool.",
    "simple": "We go back to the simple view.",
    "settings": "My settings change how the page looks.",
    "colour": "Colour the utility bars by issue splits every bar into one part per issue, the most important "
           "first.",
    "colour2": "Now each bar shows which issues make an offer good or bad for you, with a legend in the offer area.",
    "other": "You can also put the newest offer on top, show offers as small chips, or make the text larger.",
    "more": "Let us make a few more offers with the Utility Bar, and accept when the offer is good enough.",
    "accept": "This offer is better than no deal, and time is running on. We accept.",
    "results": "After the negotiation, My Results lists your negotiations so far, and Next negotiation loads "
            "the next one.",
    "bye": "That is the end of the advanced walkthrough. If your study gives you an Assistant, watch the "
        "Assistant walkthroughs next. Thank you for watching.",
}


def utility_bar(f, lo: float, hi: float) -> None:
    """Open the Utility Bar, drag a part, pick the first deal and close the popup."""
    if not f.loc(W, POPUP).count():
        f.click(W, "[data-testid=launch-generator]")
    hv.wait_for(f, W, f"{POPUP} [data-testid=range-bar-area]")
    hv.drag(f, W, f"{POPUP} [data-testid=range-bar-area]", lo, hi)
    hv.wait_for(f, W, f"{POPUP} tbody tr")
    f.click(W, f"{POPUP} tbody tr:first-child")


def main() -> None:
    with hv.server(["--no-assistant"], env_json=ENV, opponent="LinearTBNegotiator") as url:
        f = hv.film(NAME)
        hv.prewarm(f, hv.narration(globals()))
        with f:
            f.mark("Introduction")
            f.card("HANI2 walkthrough", "Negotiating against an AI", "Advanced: tools, views and settings",
                   ["Utility Bar", "Tools menu", "Reading the opponent", "Views", "My settings"])
            f.say(N["intro"], tail=0.5)
            f.say(N["recap"], tail=0.6)
            f.card_off()

            f.mark("The Utility Bar")
            f.part("1 · THE UTILITY BAR", NEC["teal"])
            hv.pane(f, W, url + "/play", sub="Against an AI")
            hv.wait_for(f, W, START)
            f.say(N["start"], wait=False)
            f.click(W, START)
            hv.my_turn(f, W)
            f.finish_speech()
            f.say(N["ubar"], caption="Utility Bar: deals by what they are worth to you", kicker="Find offers", wait=False)
            f.click(W, "[data-testid=launch-generator]")
            hv.wait_for(f, W, f"{POPUP} [data-testid=range-bar-area]")
            f.finish_speech()
            f.say(N["ubar2"], wait=False)
            f.point(W, f"{POPUP} [data-testid=range-bar-area]", hold=3.0)
            f.finish_speech(); f.unring()
            f.say(N["marks"], caption="No deal · Their offer · Your offer", kicker="Utility Bar", wait=False)
            f.point(W, f"{POPUP} >> text=No deal", hold=2.5)
            f.finish_speech(); f.unring()
            f.say(N["drag"], caption="Drag across the part you want", kicker="Utility Bar", wait=False)
            hv.drag(f, W, f"{POPUP} [data-testid=range-bar-area]", 0.6, 0.9)
            f.finish_speech()
            f.say(N["giveme"], wait=False)
            f.point(W, f"{POPUP} select", hold=1.2)
            f.frame(W).locator(f"{POPUP} select").first.select_option(label="Up to 10 offers")
            f.finish_speech(); f.unring()
            f.say(N["pick"], caption="Click a row: the deal fills your counter-offer", kicker="Utility Bar", wait=False)
            hv.wait_for(f, W, f"{POPUP} tbody tr")
            f.click(W, f"{POPUP} tbody tr:nth-child(2)")
            f.finish_speech()
            f.say(N["sent"], caption="Start high, move slowly, stay above no deal", kicker="A good habit", wait=False)
            f.click(W, f"{POPUP} button[aria-label^='Close']")
            f.click(W, SEND)
            hv.my_turn(f, W)
            f.finish_speech()

            f.mark("The Tools menu")
            f.part("2 · THE TOOLS MENU", NEC["bright"])
            f.say(N["menu"], caption="Tools: any tool in a small window", kicker="Tools", wait=False)
            f.click(W, "[data-testid=launch-tools]")
            f.sleep(1.5)
            f.finish_speech()
            f.click(W, "[role=menuitem]:has-text('Value Histogram')")
            hv.wait_for(f, W, POPUP)
            f.say(N["hist"], caption="Read the opponent from its offers", kicker="Value Histogram", wait=False)
            f.point(W, POPUP, hold=4.0)
            f.finish_speech(); f.unring()
            f.say(N["close"], wait=False)
            f.click(W, f"{POPUP} button[aria-label^='Close']")
            f.finish_speech()

            f.mark("The deadline")
            f.say(N["deadline"], caption="The deadline: the last round", kicker="Time", wait=False)
            f.point(W, "text=/Round \\d+ of \\d+/", hold=3.0)
            f.finish_speech(); f.unring()

            f.mark("Views")
            f.part("3 · VIEWS", NEC["orange"])
            f.say(N["views"], caption="Layout: simple, full, focus or bare", kicker="Views", wait=False)
            f.click(W, "button[aria-label='Layout']")
            f.sleep(1.5)
            f.finish_speech()
            f.say(N["full"], caption="The full view", kicker="Views", wait=False)
            f.click(W, "button:has-text('Full: all tool panes')")
            f.sleep(1.0)
            f.finish_speech()
            f.say(N["focus"], caption="The focus view", kicker="Views", wait=False)
            f.click(W, "button[aria-label='Layout']")
            f.click(W, "button:has-text('Focus: negotiation only')")
            f.finish_speech()
            f.say(N["simple"], wait=False)
            f.click(W, "button[aria-label='Layout']")
            f.click(W, "button:has-text('Simple: one tools area')")
            f.finish_speech()

            f.mark("My settings")
            f.part("4 · MY SETTINGS", NEC["magenta"])
            f.say(N["settings"], caption="My settings", kicker="Make it yours", wait=False)
            f.click(W, "button[aria-label='My settings']")
            f.finish_speech()
            f.say(N["colour"], caption="Colour the utility bars by issue", kicker="My settings", wait=False)
            f.click(W, "[role=dialog][aria-label='My settings'] label:has-text('Colour the utility bars by issue'), "
                       "[role=dialog][aria-label='My settings'] :text('Colour the utility bars by issue')")
            f.finish_speech()
            f.say(N["other"], wait=False)
            f.point(W, "text=Newest offer on top", hold=1.8)
            f.point(W, "text=Offers shown as", hold=1.8)
            f.point(W, "text=Text size", hold=1.5)
            f.unring()
            f.finish_speech()
            f.click(W, "button[aria-label='Close settings']")
            f.say(N["colour2"], caption="Each colour is one issue", kicker="Utility by issue", wait=False)
            f.point(W, "text=Offer on the table", hold=3.5)
            f.finish_speech(); f.unring()

            f.mark("Finishing the deal")
            f.part("5 · THE DEAL", NEC["teal"])
            f.say(N["more"], wait=False)
            for lo, hi in ((0.55, 0.8), (0.5, 0.7), (0.45, 0.65)):
                hv.my_turn(f, W)
                utility_bar(f, lo, hi)
                f.click(W, f"{POPUP} button[aria-label^='Close']")
                f.click(W, SEND)
            hv.my_turn(f, W)
            f.finish_speech()
            f.say(N["accept"], caption="Accept when the offer is good enough", kicker="Agreement", wait=False)
            f.click(W, ACCEPT_ON)
            hv.wait_for(f, W, CONFIRM_ACCEPT)
            f.sleep(2.0)
            f.click(W, CONFIRM_ACCEPT)
            hv.wait_for(f, W, "text=Agreement reached")
            f.finish_speech()
            f.say(N["results"], caption="My Results and Next negotiation", kicker="After the negotiation", wait=False)
            f.click(W, tab("My Results"))
            f.sleep(2.5)
            f.point(W, "button:has-text('Next negotiation')", hold=2.0)
            f.finish_speech(); f.unring()

            f.mark("What comes next")
            f.caption(None)
            f.part("")
            f.panes([])
            f.card("HANI2 walkthrough", "Thank you", "Next: Negotiating with an Assistant", [])
            f.say(N["bye"], tail=1.2)
        hv.finish(f, NAME)


if __name__ == "__main__":
    main()
