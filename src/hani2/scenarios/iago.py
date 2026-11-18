"""Scenarios adapted from the IAGO human-agent negotiation platform.

IAGO (used by the ANAC Human-Agent League from 2017) frames negotiation as
splitting piles of items: each side knows how many points every item is worth
to it but not to the other side. Its demonstration game was a "resource
exchange" (four goods, five of each, points from 1 to 4); the 2017 league used
piles of different sizes, with one pile both sides wanted most. The stories
and numbers here are our own.
"""

from __future__ import annotations

from .story import Issue, Side, Story

SOURCE_IAGO = "Adapted from the item-split games of the IAGO platform (ANAC Human-Agent League)."


def _split_side(me: str, piles: dict[str, int], points: dict[str, float]) -> Side:
    """Linear item values: issue values are how many items ``human`` gets;
    ``me`` gets that many (``human``) or the rest (``agent``)."""
    values = {}
    for item, n in piles.items():
        values[item] = {k: (k if me == "human" else n - k) for k in range(n + 1)}
    return Side(values=values, weights={item: points[item] * piles[item] for item in piles},
                hints={"Points per item": ", ".join(f"{item} {points[item]:g}" for item in piles)})


# --------------------------------------------------------------------------- #
# Resources: two traders split a shipment of goods                            #
# --------------------------------------------------------------------------- #
GOODS = {"Gold": 5, "Iron": 5, "Bananas": 5, "Spices": 5}
GOODS_UNITS = {"Gold": ("gold bar", "gold bars"), "Iron": ("iron bar", "iron bars"),
               "Bananas": ("crate of bananas", "crates of bananas"), "Spices": ("sack of spices", "sacks of spices")}


def _resources_setup(rng):
    # Each trader ranks the goods 1-4 (points per item); the rankings differ, so there is room to trade.
    a, h = [1, 2, 3, 4], [1, 2, 3, 4]
    rng.shuffle(a)
    rng.shuffle(h)
    return {"agent": dict(zip(GOODS, a)), "human": dict(zip(GOODS, h))}


def _trader(me: str):
    return lambda rng, ctx: _split_side(me, GOODS, ctx[me])


RESOURCES = Story(
    type="Resources",
    title="Resource Exchange",
    short_description='In this scenario, two traders split a shipment of gold, iron, bananas and spices (five items of each).',
    long_description='**The Domain** There are four issues, one per good: how many of its five items you get; your opponent gets the rest. Each item is worth some points to you (see your hints) and different points to your opponent.',
    roles={"agent": _trader("agent"), "human": _trader("human")},
    role_descriptions={"agent": "one of the two traders", "human": "one of the two traders"},
    issues=[Issue(g, list(range(n + 1)), f"How many of the {n} {GOODS_UNITS[g][1]} you get", unit=GOODS_UNITS[g])
            for g, n in GOODS.items()],
    disagreement="Without a deal the shipment is sold off at a loss.",
    human_role="human",
    setup=_resources_setup,
    source=SOURCE_IAGO + " (the resource-exchange demonstration game).",
)

# --------------------------------------------------------------------------- #
# Estate: two heirs split a grandparent's collection                          #
# --------------------------------------------------------------------------- #
ESTATE = {"Records": 6, "Clocks": 3, "Paintings": 2, "Books": 3}
ESTATE_UNITS = {"Records": ("vinyl record", "vinyl records"), "Clocks": ("antique clock", "antique clocks"),
                "Paintings": ("painting", "paintings"), "Books": ("rare book", "rare books")}


def _estate_setup(rng):
    # Both heirs value the record collection most; they differ on clocks and books; paintings vary.
    out = {}
    for heir in ("agent", "human"):
        pts = {"Records": round(rng.uniform(3.0, 4.0), 1), "Paintings": round(rng.uniform(1.0, 4.0), 1)}
        clocks_first = rng.random() < 0.5
        pts["Clocks"] = round(rng.uniform(2.0, 3.0) if clocks_first else rng.uniform(0.5, 1.5), 1)
        pts["Books"] = round(rng.uniform(0.5, 1.5) if clocks_first else rng.uniform(2.0, 3.0), 1)
        out[heir] = pts
    return out


def _heir(me: str):
    return lambda rng, ctx: _split_side(me, ESTATE, ctx[me])


ESTATE_STORY = Story(
    type="Estate",
    title="Dividing an Estate",
    short_description='In this scenario, two heirs divide a collection: six vinyl records, three clocks, two paintings and three books.',
    long_description='**The Domain** There are four issues, one per kind of item: how many you get; your opponent gets the rest. The piles have different sizes. Each item is worth some points to you (see your hints) and different points to your opponent.',
    roles={"agent": _heir("agent"), "human": _heir("human")},
    role_descriptions={"agent": "one of the two heirs", "human": "one of the two heirs"},
    issues=[Issue(k, list(range(n + 1)), f"How many of the {n} {ESTATE_UNITS[k][1]} you get", unit=ESTATE_UNITS[k])
            for k, n in ESTATE.items()],
    disagreement="Without a deal the collection is auctioned and the money split, which neither of you wants.",
    human_role="human",
    setup=_estate_setup,
    source=SOURCE_IAGO + " (the piles of different sizes follow the 2017 ANAC Human-Agent League game).",
)

STORIES = [RESOURCES, ESTATE_STORY]
