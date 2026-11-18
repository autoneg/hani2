"""Scenarios adapted from the IAGO human-agent negotiation platform.

IAGO (used by the ANAC Human-Agent League from 2017) frames negotiation as
splitting piles of items: each side knows how many points every item is worth
to it but not to the other side. Its demonstration game was a "resource
exchange" (four goods, five of each, points from 1 to 4); the 2017 league used
piles of different sizes, with one pile both sides wanted most. The stories
and numbers here are our own.

The texts, issues and roles of every type are in its template folder,
``hani2/sample_scenarios/Default/<Type>/`` (YAML, editable without code); this
module only holds the functions that draw each role's preferences.
"""

from __future__ import annotations

from .story import Side, Story



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


def _resources_setup(rng):
    # Each trader ranks the goods 1-4 (points per item); the rankings differ, so there is room to trade.
    a, h = [1, 2, 3, 4], [1, 2, 3, 4]
    rng.shuffle(a)
    rng.shuffle(h)
    return {"agent": dict(zip(GOODS, a)), "human": dict(zip(GOODS, h))}


def _trader(me: str):
    return lambda rng, ctx: _split_side(me, GOODS, ctx[me])


RESOURCES = Story.from_folder("Resources",
                              roles={"agent": _trader("agent"), "human": _trader("human")},
                              setup=_resources_setup)

# --------------------------------------------------------------------------- #
# Estate: two heirs split a grandparent's collection                          #
# --------------------------------------------------------------------------- #
ESTATE = {"Records": 6, "Clocks": 3, "Paintings": 2, "Books": 3}


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


ESTATE_STORY = Story.from_folder("Estate",
                                 roles={"agent": _heir("agent"), "human": _heir("human")},
                                 setup=_estate_setup)

STORIES = [RESOURCES, ESTATE_STORY]
