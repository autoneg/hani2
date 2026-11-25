# Offer generators

Offer generators are tools that fill your counter-offer for you. They never send it: the offer
appears in the offer panel, and you check it, change it if you like and press **Send offer**
yourself. HANI2 has three built in, in the side pane next to the offer panel by default:

| Generator | How it picks an offer | Who gets it | Best for |
|-----------|-----------------------|-------------|----------|
| [Utility-based Selector](#utility-based-selector) | A deal from a range of values for you (or, with an estimate, for the opponent) | everyone | Making offers you can accept, conceding step by step |
| [LLM](#llm) | A language model follows an instruction in plain words | admins (can be opened to participants) | Natural-language strategies, an offer together with a message |
| [Random](#random) | Any deal, at random | admins (can be opened to participants) | Exploring the outcome space, testing opponents |

An [Assistant](assistant.md) can use the same generators for you when it has the *Use tools*
ability, and you can [write your own](#writing-your-own).

## Utility-based Selector

![The Utility-based Selector](../assets/screens/tool-utility-selector.png)

1. Open the **Utility-based Selector** tab in the side pane.
2. Set **Minimum utility**: the least a deal must be worth to you, in percent of the span from your
   worst to your best deal.
3. Set **Range width**: how far above the minimum to look. 70% and 10% list every deal worth 70-80%
   to you; the default width of 100% lists every deal from the minimum up to your best.
4. Click a row to copy that deal into your counter-offer, or press **Set Offer** to have one picked
   from the range.

The table is sorted best first, can be sorted by any column and is paged for large scenarios.

**When to use it.** You know the least you will accept and want to see which deals reach it, or
you concede step by step: lower the minimum a little every round and pick the deal you like best
among those that are new.

**With an estimate of the opponent.** When an estimate of the opponent's preferences is set (for
example by your Assistant), the selector also shows what each deal is worth to the opponent *by
that estimate*, and **Choose deals by** switches the sliders to the opponent's estimated utility:
set a minimum the opponent will probably accept and pick, among those deals, the one worth most to
you. The estimate can be wrong; a banner reminds you. See [An estimate of the opponent's
preferences](tools.md#an-estimate-of-the-opponents-preferences).

![Choosing deals by the opponent's estimated utility](../assets/screens/tool-utility-selector-by-opponent.png)

## LLM

![The LLM tool](../assets/screens/tool-llm.png)

1. Open the **LLM** tab.
2. Write an instruction in plain words.
3. Choose what to generate: **Text & offer** (an offer and a message that goes with it), **Text
   only** (a message for the offer you already have) or **Offer only**.
4. Press **Generate** and read the suggestion: the offer with what it is worth to you, and the
   message.
5. Press **Apply to my offer** to copy them into your counter-offer.

Instructions that work well:

| Instruction | What it does |
|-------------|--------------|
| "Propose a fair middle ground" | A balanced offer between the two positions |
| "Improve my last offer slightly for the opponent" | A small concession |
| "Hold firm on the rent, give in on the move-in date" | Trades one issue against another |
| "Counter with a tough offer and explain why politely" | A demanding offer with a friendly message |
| "Write a short, friendly message for this offer" | With **Text only**: a message for your current offer |

The model sees the issues, your preferences, the opponent's current offer and the last turns of
the negotiation, and it is told to return an offer that exists in the scenario. It does not see the
opponent's preferences. The prompt is the `instruction_prompt` template of `llm_settings.json`
(see [Prompt templates](llms.md#prompt-templates)).

**Requirements.** A configured language model (see [Language models](llms.md); by default a local
model through Ollama) and a running negotiation. Without a model the tool shows a warning.

**When to use it.** You think in strategies rather than numbers, want a message that explains your
offer, or want to compare what a language model proposes with your own idea.

## Random

![The Random tool](../assets/screens/tool-random.png)

Press **Set Offer** to fill your counter-offer with a random deal; press it again for another.

**When to use it.** Early exploration of what is possible, breaking a deadlock with an unexpected
offer, or checking how an opponent reacts to offers far from the usual path.

## Giving the admin-only generators to participants

The LLM and Random tools are admin-only by default, so that they cannot change the conditions of a
study by accident. To offer one to participants, untick **Admins only** next to it under **Tools**
in the admin console, or set `tools.overrides.<name>.admin_only` to `false` in `env.json`. See
[Opening admin-only tools to participants](tools.md#opening-admin-only-tools-to-participants).

## Writing your own

An offer generator is a tool that derives from `hani2.tools.OutcomeSelector`. Override
`get_outcome()` to return an outcome (a tuple with one value per issue, in the scenario's issue
order) and, optionally, `selector_view()` to show controls above the **Set Offer** button the base
class adds:

```python
from hani2.tools import OutcomeSelector, ui


class HalfwayOffer(OutcomeSelector):
    name = "Halfway"
    description = "Offer the deal halfway between your best deal and the opponent's offer."
    button_label = "Meet halfway"

    def selector_view(self):
        return [ui.markdown("Picks the deal whose value for you is halfway between "
                            "your best deal and the opponent's current offer.")]

    def get_outcome(self):
        ufun, offer = self.human_ufun, self.session.partner_offer()
        if ufun is None or offer is None:
            return None
        target = (1.0 + float(ufun(offer))) / 2
        outcomes = ufun.outcome_space.enumerate_or_sample(max_cardinality=5000)
        return min(outcomes, key=lambda o: abs(float(ufun(o)) - target))
```

Save it in the tools folder (`$HANI2_HOME/tools`) and the next session has it. The [tools
tutorial](../tutorials/tools.md#offer-pickers-outcomeselector) explains `OutcomeSelector` and
everything else a tool can do.
