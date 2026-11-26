"""Walkthrough video: negotiating with an Assistant, the basics (docs/walkthroughs/hi-basics.md).

    uv run --with kokoro-onnx==0.6.1 --with numpy --with playwright \
        python scripts/videos/film_hi_basics.py [--show]

Part 1: a HANI2 server with the built-in Assistant (the local default language model,
qwen3:4b-instruct on Ollama, no opponent estimate) at the Suggest level, the Apartment Lease scenario and a conceding AI
opponent. Part 2: ``hani2 human-trial --assistant``, two people negotiating, each with an Assistant.
The Assistant's answers come from the model, so they differ from take to take.
"""

from __future__ import annotations

import hv
from hv import ASSISTANT_PANEL, COUNTER, MESSAGE, NEC, SEND, START, option

NAME = "hani2-walkthrough-hi-basics"
W, A, B = "w", "a", "b"
ENV = {"negotiation": {"n_steps": 20, "time_limit": None}}
HEADER_ASSISTANT = "header button:has-text('Assistant')"

N = {
    "intro": "In this walkthrough you negotiate with help. An Assistant, an AI helper on your side, sits next "
          "to the negotiation. You can ask it anything in plain words. And at the end, you negotiate "
          "against another person.",
    "words": "First, the words. An offer picks one option for every issue. Its utility is what it is worth to "
          "you, from zero to one hundred percent. The value on disagreement is what you get without a deal, "
          "and the deadline is when the negotiation ends.",
    "words2": "The opponent is the other side: an AI program, or another person. The Assistant is on your side, "
           "and you stay in charge.",
    "page": "The page looks as it does without an Assistant, with one more button in the header: Assistant. "
         "Its green dot says it is ready.",
    "start": "Read the Scenario Info, then start the negotiation. Your Preferences open, as usual.",
    "open": "Press Assistant to open the conversation.",
    "panel": "At the top, its name, its status and an on and off switch. Below, the conversation, and a box "
          "for your questions.",
    "ask": "Let us ask a first question, in our own words.",
    "answer": "The Assistant sees what you see: the scenario, your preferences and every offer so far. It does "
           "not see the opponent's preferences.",
    "ask2": "Now we ask it for help with our next offer.",
    "filled": "Here the Assistant may only suggest. It can fill in the counter-offer for you, but you check it "
           "and you press Send.",
    "check": "Always read a suggestion before you send it. The bar shows what the offer is worth to you, and you "
          "can change any option.",
    "sent": "We send the offer. The Assistant may be wrong: it is an AI. If you disagree, say so, or ignore it.",
    "switch": "The switch turns the Assistant off and on. While it is off, it says nothing and does nothing.",
    "people": "Now, another person. Some studies and games pair you with someone else, who sees the same "
           "scenario from the other side, often with an Assistant of their own.",
    "choice": "When the study lets you choose, the page first asks whom you want to play: a person, or an AI "
           "opponent right away.",
    "waiting": "Nobody is waiting yet, so the first player waits for the next person. Most studies also "
            "offer to play an AI instead.",
    "second": "The second player sees that one person is waiting, and joins them.",
    "both": "The negotiation starts when both have pressed Start.",
    "offer": "One side moves first. A short, friendly message helps: the other side is a person.",
    "receive": "The other side sees the offer, with a person icon instead of a robot. While it is your turn, "
            "the other page says that the opponent is deciding.",
    "reply": "People need more time than programs. Use it to ask your Assistant, then answer.",
    "end": "If one side leaves, the negotiation ends without agreement, and the page tells the other side.",
    "more": "The advanced walkthrough shows how much the Assistant may do, its estimate of what the opponent "
         "wants, and how to choose your scenario, opponent and Assistant.",
    "bye": "Thank you for watching.",
}


def part_one(f, url: str) -> None:
    f.mark("The page with an Assistant")
    f.part("1 · THE ASSISTANT", NEC["teal"])
    hv.pane(f, W, url + "/play", sub="With an Assistant")
    hv.wait_for(f, W, START)
    f.say(N["page"], caption="The Assistant button in the header", kicker="With an Assistant", wait=False)
    f.point(W, HEADER_ASSISTANT, hold=3.0)
    f.finish_speech(); f.unring()
    f.say(N["start"], wait=False)
    f.click(W, START)
    hv.my_turn(f, W)
    f.finish_speech()

    f.mark("Ask the Assistant")
    f.say(N["open"], caption="Open the conversation", kicker="Assistant", wait=False)
    f.click(W, HEADER_ASSISTANT)
    hv.wait_for(f, W, ASSISTANT_PANEL)
    f.finish_speech()
    f.say(N["panel"], wait=False)
    f.point(W, f"{ASSISTANT_PANEL} label:has([role=switch])", hold=2.0)
    f.point(W, f"{ASSISTANT_PANEL} textarea", hold=2.0)
    f.finish_speech(); f.unring()
    f.say(N["ask"], caption="Ask in your own words", kicker="Assistant", wait=False)
    hv.ask(f, W, "I have never negotiated before. Is the offer on the table good for me?")
    f.finish_speech()
    f.say(N["answer"], caption="It sees what you see, not the opponent's preferences", kicker="Assistant")
    f.sleep(2.0)

    f.mark("Let it help with your offer")
    f.say(N["ask2"], caption="Help with the next offer", kicker="Assistant", wait=False)
    hv.ask(f, W, "Please fill in a counter-offer for me that keeps the rent low.")
    f.finish_speech()
    f.say(N["filled"], caption="Suggest: it fills the offer, you send", kicker="You decide", wait=False)
    f.click(W, "button[aria-label='Close assistant']")
    if not f.loc(W, SEND).count():
        f.click(W, COUNTER)
    f.finish_speech()
    f.say(N["check"], wait=False)
    f.point(W, "text=If your opponent accepts this offer you get", hold=3.0)
    f.finish_speech(); f.unring()
    f.say(N["sent"], wait=False)
    f.click(W, SEND)
    hv.my_turn(f, W)
    f.finish_speech()
    f.say(N["switch"], caption="The on and off switch", kicker="Assistant", wait=False)
    f.click(W, HEADER_ASSISTANT)
    hv.wait_for(f, W, ASSISTANT_PANEL)
    f.point(W, f"{ASSISTANT_PANEL} label:has([role=switch])", hold=2.5)
    f.finish_speech(); f.unring()


def part_two(f, url_a: str, url_b: str) -> None:
    f.mark("Negotiating with another person")
    f.part("2 · ANOTHER PERSON", NEC["orange"])
    f.panes([])
    f.say(N["people"], caption="Two people, each with an Assistant", kicker="People")
    hv.panes2(f, [{"id": A, "name": "Alex", "sub": "Tenant", "url": url_a + "&opponent_choice=1", "color": NEC["bright"]}])
    hv.wait_for(f, A, "[data-testid=opponent-choice]")
    f.say(N["choice"], caption="Play a person, or an AI now", kicker="People", wait=False)
    f.point(A, "[data-testid=opponent-choice]", hold=3.0)
    f.finish_speech(); f.unring()
    f.say(N["waiting"], caption="Waiting for the other participant", kicker="People", wait=False)
    f.click(A, "button:has-text('Play a person')")
    f.click(A, START)
    f.finish_speech()
    hv.panes2(f, [{"id": A, "name": "Alex", "sub": "Tenant", "url": url_a + "&opponent_choice=1", "color": NEC["bright"]},
                  {"id": B, "name": "Sam", "sub": "Landlord", "url": url_b + "&opponent_choice=1", "color": NEC["orange"]}])
    hv.wait_for(f, B, "[data-testid=opponent-choice]")
    f.say(N["second"], caption="One person is waiting", kicker="People", wait=False)
    f.point(B, "[data-testid=people-waiting], [data-testid=opponent-choice]", hold=2.5)
    f.click(B, "button:has-text('Play a person')")
    f.finish_speech(); f.unring()
    f.say(N["both"], wait=False)
    hv.wait_for(f, B, START)
    f.click(B, START)
    f.finish_speech()

    f.mark("Taking turns")
    mover = None
    for _ in range(240):
        for p in (A, B):
            s = f.frame(p).locator(f"{SEND}:not([disabled])")
            if s.count():
                mover = p
        if mover:
            break
        f.sleep(0.25)
    if mover is None:
        raise RuntimeError("neither participant got the first move")
    other = B if mover == A else A
    f.say(N["offer"], caption="A short, friendly message", kicker="Taking turns", wait=False)
    f.glow(mover)
    hv.type_into(f, mover, MESSAGE, "Hello! Let us find a deal that works for both of us.")
    f.click(mover, SEND)
    f.finish_speech()
    hv.my_turn(f, other)
    f.glow(other)
    f.say(N["receive"], caption="A person icon: the other side is a person", kicker="Taking turns", wait=False)
    f.point(other, "text=Hello! Let us find a deal", hold=3.5)
    f.finish_speech(); f.unring()
    f.say(N["reply"], wait=False)
    if not f.loc(other, SEND).count():
        f.click(other, COUNTER)
    for issue in ("Rent", "Deposit"):
        f.click(other, option(issue, 3))
    hv.type_into(f, other, MESSAGE, "Thanks! Here is my proposal.")
    f.click(other, SEND)
    f.finish_speech()
    hv.my_turn(f, mover)
    f.glow(mover)
    f.say(N["end"], caption="Someone leaves: no agreement for both", kicker="Taking turns", wait=False)
    f.point(mover, "header", hold=2.0)
    f.finish_speech(); f.unring(); f.glow(mover, False)


def main() -> None:
    f = hv.film(NAME)
    hv.prewarm(f, hv.narration(globals()))
    with hv.server(["--assistant", "on"], env_json=ENV, opponent="LinearTBNegotiator",
                   assistant={"autonomy": "suggest"}) as url, \
            hv.trial_server(assistant=True, assistant_settings={"autonomy": "suggest"}) as (url_a, url_b):
        with f:
            f.mark("Introduction")
            f.card("HANI2 walkthrough", "Negotiating with an Assistant", "The basics, for first-time participants",
                   ["Ask the Assistant", "Let it help", "You decide", "Another person"])
            f.say(N["intro"], tail=0.5)
            f.card_off()
            f.mark("The words you need")
            f.tiles("The words you need", [
                {"n": "1", "t": "Offer", "d": "One option for every issue", "color": NEC["bright"]},
                {"n": "2", "t": "Utility", "d": "What a deal is worth to you, 0% to 100%", "color": NEC["blue"]},
                {"n": "3", "t": "Value on disagreement", "d": "What you get without a deal", "color": NEC["orange"]},
                {"n": "4", "t": "Deadline", "d": "When the negotiation ends", "color": NEC["magenta"]},
                {"n": "5", "t": "Opponent", "d": "The other side: an AI or a person", "color": NEC["teal"]},
                {"n": "6", "t": "Assistant", "d": "The AI helper on your side", "color": NEC["navy"]},
            ], kicker="Before we start")
            f.say(N["words"])
            f.say(N["words2"], tail=0.6)
            f.tiles_off()
            part_one(f, url)
            part_two(f, url_a, url_b)
            f.mark("What comes next")
            f.caption(None)
            f.part("")
            f.panes([])
            f.card("HANI2 walkthrough", "Thank you", "Next: Negotiating with an Assistant · advanced", [])
            f.say(N["more"], tail=0.4)
            f.say(N["bye"], tail=1.2)
        hv.finish(f, NAME)


if __name__ == "__main__":
    main()
