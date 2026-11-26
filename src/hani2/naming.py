"""Display names for the two sides of a negotiation.

Some scenarios name the sides ``human`` and ``agent`` (for example, who gets
each item on the island). With the Assistant in the session, "agent" is
ambiguous: it could be the assistant. When relabelling is on, everything the
participant or the Assistant *sees* uses ``You`` and ``Opponent`` (or the
names set in ``env.json`` → ``names``) instead, and values coming back
(offers filled by the participant, the agent or a tool) are mapped back to the
scenario's own values. Stored results, logs and what the opponent receives
keep the original values.

``env.json``::

    "names": {"apply": "auto", "self": "You", "opponent": "Opponent"}

``apply`` is ``auto`` (relabel when the session has the Assistant),
``always`` or ``never``. Only scenarios that use these words (as issue values
or role names) are relabelled.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from hani2.config import get_env

if TYPE_CHECKING:  # pragma: no cover
    from hani2.session import NegotiationSession

__all__ = ["role_labels", "relabel_value", "relabel_text", "relabel_components", "unlabel_value"]

#: scenario words that are relabelled, and which side they mean
SIDE_WORDS = {"human": "self", "agent": "opponent"}

_INPUTS = ("select", "multiselect", "radio")
_PLOT_KEYS = ("x", "y", "labels", "text", "name", "hovertext")


def role_labels(session: "NegotiationSession") -> dict[str, str]:
    """``{"human": "You", "agent": "Opponent"}`` when relabelling applies to
    this session, else ``{}``."""
    cfg = get_env("names", {}) or {}
    apply = str(cfg.get("apply", "auto")).lower()
    if apply == "never":
        return {}
    if apply != "always" and getattr(session, "support_agent", None) is None:
        return {}
    if not uses_side_words(session):
        return {}
    self_label = str(cfg.get("self") or "You")
    opp_label = str(cfg.get("opponent") or "Opponent")
    return {"human": self_label, "agent": opp_label}


def uses_side_words(session: "NegotiationSession") -> bool:
    """Whether the loaded scenario names the sides ``human`` / ``agent`` (as
    issue values or role names). Other scenarios are left alone."""
    scenario = getattr(session, "scenario", None)
    if scenario is None:
        return False
    words = set(SIDE_WORDS)
    try:
        for u in scenario.ufuns:
            if str(getattr(u, "name", "")).strip().lower() in words:
                return True
        for issue in scenario.outcome_space.issues:
            if issue.is_continuous():
                continue
            if any(isinstance(v, str) and v.strip().lower() in words for v in issue.all):
                return True
    except Exception:
        return False
    return False


def relabel_value(v: Any, m: dict[str, str]) -> Any:
    if m and isinstance(v, str):
        key = v.strip().lower()
        if key in m:
            return m[key]
        if key.endswith(" (you)") and key[:-6].strip() in m:  # negotiator ids such as "human (You)"
            return m[key[:-6].strip()]
    return v


def unlabel_value(v: Any, m: dict[str, str]) -> Any:
    """The scenario's own value for a label (``"Opponent"`` → ``"agent"``)."""
    if m and isinstance(v, str):
        for raw, label in m.items():
            if v.strip().lower() == label.lower():
                return raw
    return v


def relabel_text(text: str | None, m: dict[str, str]) -> str | None:
    """Replace the side words in free text (an offer description or the
    opponent's message), whole words only."""
    if not m or not text:
        return text
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, m)) + r")\b", re.IGNORECASE)
    return pattern.sub(lambda mo: m[mo.group(1).lower()], text)


def relabel_components(obj: Any, m: dict[str, str]) -> Any:
    """A copy of tool components with side words relabelled where they are
    *shown*: table cells, option labels, chart labels and axis values, stats
    and key/value items. Input values, option values and action names stay
    as they are, so the tool still receives its own values."""
    if not m:
        return obj
    if isinstance(obj, list):
        return [relabel_components(x, m) for x in obj]
    if not isinstance(obj, dict):
        return obj
    t = obj.get("type")
    out = dict(obj)
    if t == "table":
        out["rows"] = [{k: relabel_value(v, m) for k, v in (r or {}).items()} for r in obj.get("rows") or []]
    elif t in _INPUTS and obj.get("options"):
        out["options"] = [dict(o, label=relabel_value(o.get("label"), m)) for o in obj["options"]]
    elif t == "plot" and isinstance(obj.get("figure"), dict):
        fig = dict(obj["figure"])
        data = []
        for tr in fig.get("data") or []:
            tr = dict(tr)
            for k in _PLOT_KEYS:
                if isinstance(tr.get(k), list):
                    tr[k] = [relabel_value(v, m) for v in tr[k]]
                elif isinstance(tr.get(k), str):
                    tr[k] = relabel_value(tr[k], m)
            data.append(tr)
        fig["data"] = data
        layout = dict(fig.get("layout") or {})
        for ax in [k for k in layout if k.startswith(("xaxis", "yaxis"))]:
            if isinstance(layout[ax], dict) and isinstance(layout[ax].get("ticktext"), list):
                layout[ax] = dict(layout[ax], ticktext=[relabel_value(v, m) for v in layout[ax]["ticktext"]])
        fig["layout"] = layout
        out["figure"] = fig
    elif t == "stat":
        out["value"] = relabel_value(obj.get("value"), m)
    elif t == "kv":
        out["items"] = [[k, relabel_value(v, m)] for k, v in obj.get("items") or []]
    elif t == "legend":
        out["items"] = [dict(i, label=relabel_value(i.get("label"), m)) for i in obj.get("items") or []]
    elif t == "outcome":
        out["values"] = {k: relabel_value(v, m) for k, v in (obj.get("values") or {}).items()}
    if isinstance(obj.get("children"), list):
        out["children"] = relabel_components(obj["children"], m)
    return out
