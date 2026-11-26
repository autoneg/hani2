"""Walkthrough video: negotiating against an AI, the basics (docs/walkthroughs/han-basics.md).

    uv run --with kokoro-onnx==0.6.1 --with numpy --with playwright \
        python scripts/videos/film_han_basics.py [--show]

A fresh HANI2 server without an Assistant, the Apartment Lease scenario and a steadily conceding
AI opponent; the participant is the tenant.
"""

from __future__ import annotations

import hv
from hv import ACCEPT_ON, CANCEL, CONFIRM_ACCEPT, CONFIRM_END, COUNTER, END_BTN, MESSAGE, NEC, SEND, START, option, tab

NAME = "hani2-walkthrough-han-basics"
W = "w"
ENV = {"negotiation": {"n_steps": 20, "time_limit": None}}

N = {
    "intro": "Welcome. In this walkthrough you negotiate against an AI for the first time. You need no "
          "experience at all: we explain every word on the screen as we go, and we end with your first deal.",
    "words1": "A negotiation is two sides taking turns to agree on a deal. A deal settles several issues, "
           "and each issue has a few options to choose from.",
    "words2": "An offer picks one option for every issue. Its utility is how much that deal is worth to you, "
           "from zero percent to one hundred percent.",
    "words3": "The value on disagreement is what you get if there is no deal at all. And the deadline is "
           "when the negotiation ends, with or without a deal.",
    "page": "This is the negotiation page, before the negotiation starts.",
    "welcome": "At the bottom, the welcome text says who you negotiate with: an AI opponent, a computer "
            "program that plays the other side.",
    "info": "On the right, the Scenario Info tells the story. Here, a landlord and a tenant negotiate the "
         "lease of an apartment. You are the tenant.",
    "issues": "The table lists the four issues, the rent, the deposit, the move-in date and the lease "
           "length, with their options.",
    "hints": "The hints tell you your role and which issue matters most to you. When you are ready, press "
          "Start negotiation.",
    "prefs": "As the negotiation starts, your Preferences open. They show how much each possible deal is "
          "worth to you.",
    "inshort": "In short: every deal is worth between zero and one hundred percent to you, and some "
            "issues count more than others.",
    "weights": "The ring shows the issue weights. A bigger slice is a more important issue, and the "
            "slices add up to one hundred percent. The numbers are round, so you can add them in your head.",
    "values": "Below it, pick an issue to see what each of its options is worth to you.",
    "header": "Now the page itself. The header shows the scenario, your role and the round. The negotiation "
           "has a deadline: a fixed number of rounds.",
    "first": "The opponent made the first offer. It appears in the history, and as the offer on the table.",
    "worth": "The bar shows what this offer is worth to you. The small dark line marks your value on "
          "disagreement. A bar that stops before the line means the offer is worse than no deal.",
    "buttons": "On your turn you have three choices. Accept takes the offer. End stops without a deal. "
            "Both show what you would get.",
    "counter": "Or make a counter-offer: a deal of your own. Press Counter-offer to open the editor.",
    "pick": "Click the option you want for each issue. Asking for everything rarely works: give way on "
         "what matters little to you.",
    "gauge": "This bar shows what your offer is worth to you if the opponent accepts it.",
    "msg": "You can add a short message, then press Send offer.",
    "wait": "Your offer appears on the right of the history, and the opponent answers on its turn.",
    "rounds": "Let us exchange a few more offers. Watch the opponent's offers get better for you, round "
           "after round.",
    "end": "If no deal looks good enough, End stops the negotiation. The window tells you what you get "
        "without a deal. We cancel, and keep negotiating.",
    "accept": "This offer is better than no deal, so we accept it. The window shows the offer and what "
           "you will receive.",
    "agreed": "Agreement reached! The deal and what it is worth to you are shown here, and Next "
           "negotiation loads the next one.",
    "more": "That is all you need to negotiate. The advanced walkthrough shows the tools that find good "
         "offers for you, the views of the page and your settings.",
    "bye": "Thank you for watching, and good luck with your negotiations.",
}


def main() -> None:
    with hv.server(["--no-assistant"], env_json=ENV, opponent="LinearTBNegotiator") as url:
        f = hv.film(NAME)
        hv.prewarm(f, hv.narration(globals()))
        with f:
            f.mark("Introduction")
            f.card("HANI2 walkthrough", "Negotiating against an AI", "The basics, for first-time participants",
                   ["Offers", "What deals are worth", "Counter-offers", "Accept or end"])
            f.say(N["intro"], tail=0.6)
            f.card_off()

            f.mark("The words you need")
            f.tiles("The words you need", [
                {"n": "1", "t": "Issue and option", "d": "What the deal settles, and the choices for each", "color": NEC["bright"]},
                {"n": "2", "t": "Offer", "d": "One option for every issue", "color": NEC["teal"]},
                {"n": "3", "t": "Utility", "d": "What a deal is worth to you, 0% to 100%", "color": NEC["blue"]},
                {"n": "4", "t": "Value on disagreement", "d": "What you get without a deal", "color": NEC["orange"]},
                {"n": "5", "t": "Deadline", "d": "When the negotiation ends", "color": NEC["magenta"]},
            ], kicker="Before we start")
            f.say(N["words1"])
            f.say(N["words2"])
            f.say(N["words3"], tail=0.6)
            f.tiles_off()

            f.mark("Before you start")
            f.part("1 · BEFORE YOU START", NEC["teal"])
            hv.pane(f, W, url + "/play", sub="Against an AI")
            hv.wait_for(f, W, START)
            f.say(N["page"], caption="The negotiation page", kicker="Before you start")
            f.say(N["welcome"], wait=False)
            f.point(W, "text=Welcome", hold=2.5)
            f.finish_speech(); f.unring()
            f.say(N["info"], caption="Scenario Info: the story and your role", kicker="Before you start", wait=False)
            f.point(W, tab("Scenario Info"), hold=2.0)
            f.point(W, "text=You act as Tenant", hold=1.5)
            f.finish_speech(); f.unring()
            f.say(N["issues"], wait=False)
            f.point(W, "table", hold=2.5)
            f.finish_speech(); f.unring()
            f.say(N["hints"], caption="Hints: your role and what matters most", wait=False)
            f.point(W, "text=Most important issue", hold=2.5)
            f.unring()
            f.finish_speech()
            f.click(W, START)

            f.mark("What deals are worth to you")
            f.part("2 · WHAT DEALS ARE WORTH", NEC["bright"])
            hv.wait_for(f, W, "text=In short")
            f.say(N["prefs"], caption="Preferences: what each deal is worth to you", kicker="Utility")
            f.say(N["inshort"], wait=False)
            f.point(W, "text=In short", hold=2.5)
            f.finish_speech(); f.unring()
            f.say(N["weights"], caption="Issue weights add up to 100%", kicker="Utility", wait=False)
            f.point(W, "text=Issue weights", hold=3.0)
            f.finish_speech(); f.unring()
            f.say(N["values"], wait=False)
            f.point(W, "text=Value of each option", hold=2.0)
            f.finish_speech(); f.unring()

            f.mark("The negotiation page")
            f.part("3 · THE PAGE", NEC["orange"])
            f.say(N["header"], caption="The header: role, round and deadline", kicker="The page", wait=False)
            f.point(W, "header", hold=1.0)
            f.point(W, "text=/Round \\d+ of \\d+/", hold=2.5)
            f.finish_speech(); f.unring()
            hv.my_turn(f, W)
            f.say(N["first"], caption="The offer on the table", kicker="The page", wait=False)
            f.point(W, "text=Offer on the table", hold=3.0)
            f.finish_speech(); f.unring()
            f.say(N["worth"], caption="The dark line: your value on disagreement", kicker="Worth to you", wait=False)
            f.point(W, "text=Worth to you · line marks no-deal value", hold=4.0)
            f.finish_speech(); f.unring()
            f.say(N["buttons"], caption="Accept · Counter-offer · End", kicker="Your turn", wait=False)
            f.point(W, ACCEPT_ON, hold=2.5)
            f.point(W, END_BTN, hold=2.5)
            f.finish_speech(); f.unring()

            f.mark("Make a counter-offer")
            f.part("4 · COUNTER-OFFER", NEC["teal"])
            f.say(N["counter"], caption="Counter-offer: a deal of your own", kicker="Your turn", wait=False)
            f.click(W, COUNTER)
            f.finish_speech()
            f.say(N["pick"], caption="One option per issue", kicker="Counter-offer", wait=False)
            f.click(W, option("Rent", 2))
            f.click(W, option("Deposit", 2))
            f.click(W, option("Lease length", 4))
            f.finish_speech()
            f.say(N["gauge"], wait=False)
            f.point(W, "text=If your opponent accepts this offer you get", hold=2.5)
            f.finish_speech(); f.unring()
            f.say(N["msg"], caption="An optional message, then Send offer", kicker="Counter-offer", wait=False)
            hv.type_into(f, W, MESSAGE, "I can pay a bit more rent if the deposit is lower.")
            f.click(W, SEND)
            f.finish_speech()
            f.say(N["wait"], wait=False)
            hv.my_turn(f, W)
            f.finish_speech()

            f.part("5 · ROUNDS", NEC["bright"])
            f.say(N["rounds"], caption="Offers move round after round", kicker="The history", wait=False)
            for issue, n in (("Rent", 3), ("Move-in date", 3), ("Deposit", 3)):
                hv.my_turn(f, W)
                if not f.loc(W, SEND).count():
                    f.click(W, COUNTER)
                f.click(W, option(issue, n))
                f.click(W, SEND)
            hv.my_turn(f, W)
            f.finish_speech()

            f.mark("Accept or end")
            f.part("6 · ACCEPT OR END", NEC["orange"])
            f.say(N["end"], caption="End: what you get without a deal", kicker="Value on disagreement", wait=False)
            f.click(W, END_BTN)
            hv.wait_for(f, W, CONFIRM_END)
            f.sleep(3.5)
            f.click(W, CANCEL)
            f.finish_speech()

            f.say(N["accept"], caption="Accept: confirm the deal", kicker="Agreement", wait=False)
            f.click(W, ACCEPT_ON)
            hv.wait_for(f, W, CONFIRM_ACCEPT)
            f.sleep(2.5)
            f.click(W, CONFIRM_ACCEPT)
            f.finish_speech()
            hv.wait_for(f, W, "text=Agreement reached")
            f.say(N["agreed"], caption="Agreement reached", kicker="Your first deal", wait=False)
            f.point(W, "text=Agreement reached", hold=3.0)
            f.finish_speech(); f.unring()

            f.mark("What comes next")
            f.caption(None)
            f.part("")
            f.panes([])
            f.tiles("In the advanced walkthrough", [
                {"n": "A", "t": "Utility Bar", "d": "Find deals by what they are worth to you", "color": NEC["bright"]},
                {"n": "B", "t": "Tools menu", "d": "Any tool in a small window", "color": NEC["teal"]},
                {"n": "C", "t": "Views", "d": "Simple, full, focus or bare", "color": NEC["orange"]},
                {"n": "D", "t": "My settings", "d": "Bars coloured by issue, and more", "color": NEC["magenta"]},
            ], kicker="Next", cols=2)
            f.say(N["more"], tail=0.6)
            f.tiles_off()
            f.card("HANI2 walkthrough", "Thank you", "Next: Negotiating against an AI · advanced", [])
            f.say(N["bye"], tail=1.2)
        hv.finish(f, NAME)


if __name__ == "__main__":
    main()
