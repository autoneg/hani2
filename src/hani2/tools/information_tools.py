"""Tools for what only the human knows in a negotiation (see :mod:`hani2.information`).

* :class:`PastNegotiationsTool` lists the past negotiations the human holds and
  shows any one of them offer by offer.
* :class:`MarketResearchTool` shows the market research when the human is
  given it.
* :class:`BriefingTool` shows the human's private briefings (instructions and
  limits that are not in their preferences) and what only they may do.

Both are offered only in rounds where the human has something to show, and the
Assistant cannot read them while the human and the Assistant know different things.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

from hani2.tools import ui
from hani2.tools.base import Tool
from hani2.tools.plotting import AGENT_COLOR, HUMAN_COLOR, base_layout

__all__ = ["BriefingTool", "PastNegotiationsTool", "MarketResearchTool"]


def _pct(v: Any) -> str:
    try:
        return f"{float(v):.0%}"
    except (TypeError, ValueError):
        return "—"


def _percent_formats(rows: list[dict], *cols: str) -> dict[str, str]:
    present = {k for r in rows for k in r}
    return {c: "percent" for c in cols if c in present}


def _holder_text(n_other: int, assistant_has: bool) -> str:
    if not n_other:
        return ""
    if not assistant_has:
        return ""
    return f" Your Assistant has {n_other} more that you cannot see; ask it what they show."


class BriefingTool(Tool):
    name = "Briefing"
    groups = ("information",)
    description = "Your private instructions for this negotiation."
    help = """
    **What it shows.** Instructions only you have, such as a limit set by someone you
    negotiate for ("your manager will not approve a rent above 3200"). They are not part of
    your preferences, and your Assistant does not see them unless you tell it.

    **How to use it.** Keep to them. If your Assistant suggests something that breaks one,
    tell it about the limit.
    """
    icon = "clipboard-list"
    pane = "upper"
    timing = "load"
    order = 2
    private_information = True

    def available(self) -> bool:
        st = self.information
        return bool(st.briefings_for("human") or st.human_only_issues or st.human_only_actions)

    def private_now(self) -> bool:
        return any(b["to"] == "human" for b in self.information.briefings)

    def view(self):
        from hani2.information import constraint_text

        st = self.information
        comps: list[ui.Component] = []
        for b in st.briefings_for("human"):
            items: list[ui.Component] = [ui.markdown(self.session.relabel_text(b["text"]) or b["text"])]
            limits = [t for t in (constraint_text(c) for c in b.get("constraints") or []) if t]
            if limits and any(t not in b["text"] for t in limits):
                items.append(ui.kv({f"Limit {k + 1}": t for k, t in enumerate(limits)}, title="Your limits"))
            note = "Your Assistant knows this too." if b["to"] == "both" else "Your Assistant does not know this."
            items.append(ui.text_block(note, muted=True))
            comps.append(ui.card(*items, title="Private briefing"))
        if st.human_only_issues or st.human_only_actions:
            rows = {}
            if st.human_only_issues:
                rows["Issues only you set"] = ", ".join(st.human_only_issues)
            if st.human_only_actions:
                rows["Only you can"] = st.decisions_text(include_issues=False)
            comps.append(ui.card(ui.kv(rows), ui.text_block("Your Assistant can suggest these, but only you decide.",
                                                            muted=True), title="Your decisions"))
        return comps or [ui.text_block("No private briefing in this negotiation.", muted=True)]


class PastNegotiationsTool(Tool):
    name = "Past Negotiations"
    groups = ("information",)
    description = "Earlier negotiations in this scenario between parties like you and your opponent."
    help = """
    **What it shows.** Records of earlier negotiations in this same scenario. The party in
    your role had preferences like yours, and its opponent preferences like your opponent's
    (how alike depends on the study). The table lists them; pick one to see every offer.

    **How to use it.** Look at what the opponent side usually ends up accepting, how fast it
    concedes and which deals were reached. Your Assistant may hold other records than you:
    ask it what they show.
    """
    icon = "history"
    pane = "upper"
    timing = "load"
    order = 3
    private_information = True

    def available(self) -> bool:
        return bool(self.information.human_past)

    def private_now(self) -> bool:
        st = self.information
        return any(pid not in st.assistant_past for pid in st.human_past)

    def view(self):
        from hani2.information import past_view

        st = self.information
        mine = st.held_by("human")
        if not mine:
            return [ui.text_block("You have no past negotiations in this scenario.", muted=True)]
        sess = self.session
        others = [i for i in st.assistant_past if i not in st.human_past]
        intro = (f"You have {len(mine)} past negotiation{'s' if len(mine) != 1 else ''} in this scenario."
                 + _holder_text(len(others), bool(others)))
        views = [past_view(sess, r) for r in mine]
        utilities = st.past_utilities("human")
        rows = []
        for v in views:
            row = {"Id": v["id"], "Result": v["agreement_text"] if v["result"] == "agreement" else "No agreement",
                   "Rounds": v["rounds"], "Your side played": v["styles"]["your_side"],
                   "Opponent played": v["styles"]["opponent"]}
            if utilities in ("own", "both"):
                row["Your side got"] = v["final_utilities"].get("your_side")
            if utilities == "both":
                row["Opponent got"] = v["final_utilities"].get("opponent")
            rows.append(row)
        ids = [v["id"] for v in views]
        sel = self.values.get("negotiation")
        if sel not in ids:
            sel = ids[0]
        chosen = next(v for v in views if v["id"] == sel)
        comps: list[ui.Component] = [
            ui.alert(intro, "info"),
            ui.table(rows, formats=_percent_formats(rows, "Your side got", "Opponent got"), sortable=True,
                     page_size=20, on_select="pick", selected=ids.index(sel)),
            ui.select("negotiation", ids, sel, label="Show negotiation"),
            *self._details(chosen, utilities),
        ]
        return comps

    def _details(self, v: dict[str, Any], utilities: str) -> list[ui.Component]:
        stats = [ui.stat("Result", "Agreement" if v["result"] == "agreement" else "No agreement"),
                 ui.stat("Rounds", v["rounds"])]
        if "your_side" in v["final_utilities"]:
            stats.append(ui.stat("Your side got", _pct(v["final_utilities"]["your_side"]),
                                 hint="by its own preferences"))
        if "opponent" in v["final_utilities"]:
            stats.append(ui.stat("Opponent got", _pct(v["final_utilities"]["opponent"]),
                                 hint="by its own preferences"))
        comps: list[ui.Component] = [ui.stats(*stats)]
        if v["result"] == "agreement":
            comps.append(ui.text_block(f"Agreement: {v['agreement_text']}"))
        if utilities in ("own", "both") and v["offers"]:
            fig = go.Figure()
            for side, color, label in (("your side", HUMAN_COLOR, "Your side"), ("opponent", AGENT_COLOR, "Opponent")):
                pts = [o for o in v["offers"] if o["by"] == side]
                key = "utility_your_side"
                if pts and any(o.get(key) is not None for o in pts):
                    fig.add_trace(go.Scatter(x=[o["step"] for o in pts], y=[100 * float(o[key]) for o in pts],
                                             mode="lines+markers", name=f"{label}'s offers", line=dict(color=color)))
            fig.update_layout(**base_layout(240, xaxis_title="Round", yaxis_title="Worth to your side (%)"))
            comps.append(ui.card(ui.plot(fig), title="How the offers moved"))
        offer_rows = []
        for o in v["offers"]:
            r = {"Round": o["step"], "By": "Your side" if o["by"] == "your side" else "Opponent", "Offer": o["text"]}
            if "utility_your_side" in o:
                r["Worth to your side"] = o["utility_your_side"]
            if "utility_opponent" in o:
                r["Worth to opponent"] = o["utility_opponent"]
            offer_rows.append(r)
        comps.append(ui.card(ui.table(offer_rows, formats=_percent_formats(offer_rows, "Worth to your side", "Worth to opponent"),
                                      sortable=False, page_size=50), title=f"Every offer of {v['id']}",
                             collapsible=True, collapsed=False))
        return comps

    def on_action(self, action: str, payload: dict[str, Any]) -> None:
        if action == "pick":
            row = payload.get("row") or {}
            if row.get("Id"):
                self.values["negotiation"] = row["Id"]
                self.refresh()


class MarketResearchTool(Tool):
    name = "Market Research"
    groups = ("information",)
    description = "What a market study says about the preferences of parties in this scenario."
    help = """
    **What it shows.** Typical preferences of parties in this scenario, from a study of many
    comparable negotiators: which issues usually matter most to them, which option of each
    issue they most often like best, the deal they would like most and what they usually get
    without an agreement.

    **How to use it.** It describes parties *like* your opponent, not your opponent itself:
    use it as a first guess and check it against the offers you receive.
    """
    icon = "chart-pie"
    pane = "upper"
    timing = "load"
    order = 4
    private_information = True

    def available(self) -> bool:
        return self.information.human_market

    def private_now(self) -> bool:
        return self.information.human_market and not self.information.assistant_market

    def view(self):
        from hani2.information import market_view

        mv = market_view(self.session) if self.information.human_market else None
        if not mv:
            return [ui.text_block("No market research for this scenario.", muted=True)]
        comps: list[ui.Component] = [ui.text_block(f"Based on {mv['based_on']}.", muted=True)]
        if mv.get("notes"):
            comps.append(ui.card(ui.markdown(str(mv["notes"]), size="sm"), title="Notes"))
        for key, title in (("opponent", "Parties like your opponent"), ("your_side", "Parties in your role")):
            rec = mv.get(key)
            if not rec:
                continue
            items: list[ui.Component] = []
            if rec.get("issue_weights"):
                rows = [{"Issue": k, "Typical weight": w["mean"], "Spread (±)": w["spread"],
                         "Usually best option": str((rec.get("favourite_options") or {}).get(k, {}).get("option", "")),
                         "How often": (rec.get("favourite_options") or {}).get(k, {}).get("share")}
                        for k, w in sorted(rec["issue_weights"].items(), key=lambda kv: -kv[1]["mean"])]
                items.append(ui.table(rows, formats={"Typical weight": "percent", "Spread (±)": "percent",
                                                     "How often": "percent"}, sortable=False))
            if rec.get("likely_best_deal"):
                items.append(ui.kv({k: str(v) for k, v in rec["likely_best_deal"].items()}, title="Their most likely best deal"))
                if rec.get("likely_best_deal_text"):
                    items.append(ui.text_block(f"In words: {rec['likely_best_deal_text']}", muted=True))
            vd = rec.get("value_on_disagreement") or {}
            if vd:
                rng = vd.get("range") or [None, None]
                items.append(ui.stat("Value on disagreement", _pct(vd.get("typical")),
                                     hint=f"usually between {_pct(rng[0])} and {_pct(rng[1])}"))
            if rec.get("notes"):
                items.append(ui.markdown(str(rec["notes"]), size="sm"))
            comps.append(ui.card(*items, title=title))
        return comps
