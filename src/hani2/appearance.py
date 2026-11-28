"""A different look for the Assistant and the opponent in each negotiation.

With ``interface.vary_appearance`` (env.json: the settings folder, a project or a study) the
Assistant and/or the opponent get a colour and an icon of their own in every negotiation of a
participant, so that each negotiation's Assistant (and opponent) looks like a different one.

The looks are fixed per participant: a permutation of the colours and of the icons, seeded by
the participant and the study, is walked negotiation by negotiation (practice included). Two
consecutive negotiations therefore never share a colour or an icon, the same participant gets
the same sequence after a reload, and different participants see the looks in different orders
(so a look is not confounded with the negotiation's position).

The server sends keys only (``violet``, ``sparkles``, …); the page maps them to theme-aware
colours and icons. The Assistant's and the opponent's colours never overlap, and none is the
participant's own colour.
"""

from __future__ import annotations

import random
from typing import Any

#: colours of the Assistant (none is the participant's own blue, an opponent's, or close to the
#: good / bad / warning colours of the page)
ASSISTANT_COLORS = ("violet", "fuchsia", "cyan", "slate")
#: icons of the Assistant
ASSISTANT_ICONS = ("bot", "sparkles", "brain-circuit", "lightbulb", "wand-sparkles", "compass", "feather")
#: colours of the opponent
OPPONENT_COLORS = ("orange", "brown", "olive")
#: icons of an AI opponent (a human opponent keeps the person icon; only its colour changes)
OPPONENT_ICONS = ("bot", "briefcase", "building-2", "store", "landmark", "factory", "globe")

#: env.json → interface.vary_appearance: both off unless switched on
DEFAULT_VARY = {"assistant": False, "opponent": False}


def vary_flags(value: Any) -> dict[str, bool]:
    """``interface.vary_appearance`` as ``{"assistant": bool, "opponent": bool}``: ``true`` or
    ``false`` sets both; a mapping sets each (a missing key is off)."""
    if isinstance(value, bool):
        return {"assistant": value, "opponent": value}
    if isinstance(value, str):
        on = value.strip().lower() in ("1", "true", "yes", "on")
        return {"assistant": on, "opponent": on}
    if isinstance(value, dict):
        return {k: bool(value.get(k, False)) for k in DEFAULT_VARY}
    return dict(DEFAULT_VARY)


def _pick(options: tuple[str, ...], seed: str, index: int) -> str:
    order = list(options)
    random.Random(seed).shuffle(order)  # a string seed is stable across runs (unlike hash())
    return order[index % len(order)]


def look_for(seed: str, index: int, flags: dict[str, bool]) -> dict[str, Any] | None:
    """The look of negotiation ``index`` (0 = the participant's first) of the participant ``seed``:
    ``{"index": i, "assistant": {"color", "icon"} | None, "opponent": {"color", "icon"} | None}``,
    or ``None`` when neither varies."""
    if not any(flags.values()):
        return None
    out: dict[str, Any] = {"index": int(index), "assistant": None, "opponent": None}
    if flags.get("assistant"):
        out["assistant"] = {"color": _pick(ASSISTANT_COLORS, f"{seed}|assistant|color", index),
                            "icon": _pick(ASSISTANT_ICONS, f"{seed}|assistant|icon", index)}
    if flags.get("opponent"):
        out["opponent"] = {"color": _pick(OPPONENT_COLORS, f"{seed}|opponent|color", index),
                           "icon": _pick(OPPONENT_ICONS, f"{seed}|opponent|icon", index)}
    return out
