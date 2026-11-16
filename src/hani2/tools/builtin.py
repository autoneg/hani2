"""The built-in tools."""

from __future__ import annotations

import pickle
import random
from pathlib import Path
from typing import Any

import numpy as np
import plotly.graph_objects as go
from negmas import LinearAdditiveUtilityFunction, LinearUtilityAggregationFunction, Outcome

from hani2.tools import ui
from hani2.tools.base import OutcomeSelector, Tool
from hani2.tools.plotting import (
    AGENT_COLOR,
    HUMAN_COLOR,
    SEQUENCE,
    base_layout,
    party_color,
    trace_frame,
)

__all__ = [
    "PreferencesTool",
    "AgentPreferencesTool",
    "ScenarioInfoTool",
    "UtilityPlotTool",
    "OutcomePlotTool",
    "TraceTool",
    "ValueHistogramTool",
    "UserResultsTool",
    "AllResultsTool",
    "UtilitySelectorTool",
    "RandomOutcomeTool",
    "ResponseGeneratorTool",
]

PREFERENCES_HELP_MD = """
Your **preferences** say how good each possible agreement is *for you*, on a
scale from **0% (worst) to 100% (best)**. Your AI partner has its own
preferences, and you usually value things differently — that difference is
what makes a deal worth doing.

**How a deal's value is worked out**

An agreement fixes one option for every *issue* (for example a price, a
quantity or a delivery time). Each issue contributes in two steps:

- **Issue value** — within one issue, each option is worth a percentage to you
  (the bar chart). 100% is your favourite option for that issue, 0% your least
  favourite.
- **Issue weight** — issues are not equally important. The donut chart shows
  how much each issue *weighs*; the weights add up to 100%.

Your total score for a deal is the **weighted sum** of the issue values:

> total = weight₁ × value₁ + weight₂ × value₂ + …

The **value on disagreement** is what you get if the negotiation ends with
**no agreement**. A deal worth *more* than that beats walking away; a deal
worth *less* is worse than no deal at all.

**Worked example (Price and Delivery)**

Price weighs **70%** and Delivery **30%**; Price $10 → 100%, $20 → 50%;
Delivery Fast → 100%, Slow → 20%.

- Deal A — *$20, Fast*: 0.7 × 50% + 0.3 × 100% = **65%**
- Deal B — *$10, Slow*: 0.7 × 100% + 0.3 × 20% = **76%**

Deal B is better for you: a low price matters enough that you would accept
slow delivery to get it.
"""


# --------------------------------------------------------------------------- #
# Preferences                                                                  #
# --------------------------------------------------------------------------- #
def _issue_values(ufun, index: int) -> tuple[list, list[float]]:
    issue = ufun.outcome_space.issues[index]
    if issue.is_continuous():
        labels = list(np.linspace(issue.min_value, issue.max_value, num=20, endpoint=True))
    else:
        labels = list(issue.all)
    fun = ufun.values[index]
    return labels, [100 * float(fun(v)) for v in labels]


def preference_view(tool: Tool, ufun, *, title_prefix: str = "", help_card: bool = True) -> list[ui.Component]:
    if ufun is None:
        return [ui.text_block("No preferences loaded yet.", muted=True)]
    issues = list(ufun.outcome_space.issues)
    names = [i.name for i in issues]
    selected = tool.values.get("issue", names[0] if names else None)
    if selected not in names and names:
        selected = names[0]
    comps: list[ui.Component] = []
    if isinstance(ufun, LinearUtilityAggregationFunction) or hasattr(ufun, "weights"):
        weights = [float(w) for w in ufun.weights]
        fig = go.Figure(
            data=[go.Pie(labels=names, values=weights, hole=0.55, textinfo="label+percent",
                         marker=dict(colors=SEQUENCE * 4), sort=False)]
        )
        fig.update_layout(**base_layout(220, legend=False, margin=dict(l=8, r=8, t=8, b=8)))
        weights_card = ui.card(ui.plot(fig), title=f"{title_prefix}Issue weights")
    else:
        weights_card = ui.alert("This utility function is not additive; weights are not available.", "neutral")
    issue_comps: list[ui.Component] = [ui.select("issue", names, selected, label="Issue")]
    if isinstance(ufun, LinearAdditiveUtilityFunction) and selected is not None:
        idx = names.index(selected)
        labels, vals = _issue_values(ufun, idx)
        fig = go.Figure(
            data=[go.Bar(y=[str(v) for v in labels], x=vals, orientation="h", marker_color=HUMAN_COLOR,
                         hovertemplate="%{y}: %{x:.0f}%<extra></extra>")]
        )
        fig.update_layout(**base_layout(max(160, 26 * len(labels) + 40), legend=False,
                                        xaxis=dict(range=[0, 100], ticksuffix="%"),
                                        yaxis=dict(type="category", autorange="reversed")))
        issue_comps.append(ui.plot(fig))
    rv = float(getattr(ufun, "reserved_value", 0.0) or 0.0)
    comps.append(
        ui.grid(
            ui.column(weights_card, ui.stat("Value on disagreement", f"{rv:.1%}",
                                            hint="What you get if no agreement is reached")),
            ui.card(*issue_comps, title=f"{title_prefix}Value of each option"),
            cols=2,
        )
    )
    if help_card:
        comps.append(ui.card(ui.markdown(PREFERENCES_HELP_MD, size="sm"), title="How your preferences work",
                             collapsible=True, collapsed=True))
    return comps


class PreferencesTool(Tool):
    name = "Preferences"
    description = "Your issue weights, the value of every option and your value on disagreement."
    icon = "sliders-horizontal"
    pane = "upper"
    timing = "load"
    permanent = True
    order = 0

    def view(self):
        return preference_view(self, self.human_ufun)


class AgentPreferencesTool(Tool):
    name = "Agent Preferences"
    description = "The AI partner's private preferences (admins only)."
    icon = "bot"
    pane = "upper"
    timing = "load"
    admin_only = True
    order = 50

    def view(self):
        return [ui.alert("Only visible to administrators.", "warning"),
                *preference_view(self, self.agent_ufun, title_prefix="Agent ", help_card=False)]


# --------------------------------------------------------------------------- #
# Scenario info                                                                #
# --------------------------------------------------------------------------- #
class ScenarioInfoTool(Tool):
    name = "Scenario Info"
    description = "The scenario description, the issues and hints for your role."
    icon = "book-open"
    pane = "upper"
    timing = "load"
    permanent = True
    order = 1

    def view(self):
        s = self.scenario
        if s is None:
            return [ui.text_block("No scenario loaded.", muted=True)]
        info = s.info or {}
        role = str(self.session_state.get("human_id", "")).replace(" (You)", "")
        descs = info.get("issue_description", {}) or {}
        rows = []
        for issue in s.outcome_space.issues:
            d = descs.get(role, {}).get(issue.name, "") if isinstance(descs.get(role), dict) else descs.get(issue.name, "")
            vals = (f"{issue.min_value} – {issue.max_value}" if issue.is_continuous() or issue.cardinality > 12
                    else ", ".join(str(v) for v in issue.all))
            rows.append({"Issue": issue.name, "Options": vals, "Description": d or ""})
        comps: list[ui.Component] = [
            ui.heading(info.get("title") or str(s.outcome_space.name), 3),
            ui.row(ui.badge(f"You act as {role}", "primary")),
        ]
        if info.get("short_description"):
            comps.append(ui.markdown(info["short_description"]))
        comps.append(ui.table(rows, ["Issue", "Options", "Description"], sortable=False, page_size=50))
        hints = (info.get("hints") or {}).get(role) or {}
        if hints:
            comps.append(ui.kv(hints, title="Hints"))
        if info.get("long_description"):
            comps.append(ui.card(ui.markdown(info["long_description"], size="sm"), title="Full description",
                                 collapsible=True, collapsed=True))
        return comps


# --------------------------------------------------------------------------- #
# Plots                                                                        #
# --------------------------------------------------------------------------- #
class UtilityPlotTool(Tool):
    name = "Utility Plot"
    description = "How the utility of the offers evolves over time."
    icon = "chart-line"
    pane = "lower"
    timing = "start"
    enabled = False
    order = 10

    def view(self):
        m = self.mechanism
        if m is None:
            return [ui.text_block("Starts with the negotiation.", muted=True)]
        human_id = self.session_state.get("human_id")
        show_agent = bool(self.values.get("show_agent", False)) and self.is_admin
        time_cols = {"relative_time": "Relative time", "step": "Step", "time": "Time (s)"}
        ycols = {"human": "Your utility"} | ({"agent": "Agent utility"} if show_agent else {})
        x = self.values.get("x", "step")
        if x not in list(time_cols) + list(ycols):
            x = "step"
        y = self.values.get("y", "human")
        if y not in ycols:
            y = "human"
        df = trace_frame(self.trace())
        fig = go.Figure()
        if len(df):
            df["human"] = df["offer"].apply(lambda o: 100 * float(self.human_ufun(o)) if o is not None else None)
            if show_agent:
                df["agent"] = df["offer"].apply(lambda o: 100 * float(self.agent_ufun(o)) if o is not None else None)
            for neg in df["negotiator"].unique():
                sub = df[df["negotiator"] == neg]
                fig.add_trace(go.Scatter(
                    x=sub[x] * (100 if x in ycols else 1) / (100 if x in ycols else 1), y=sub[y],
                    mode="lines+markers", name="You" if str(neg) == str(human_id) else "Partner",
                    line=dict(color=party_color(neg, human_id), width=2.5, shape="spline"),
                    marker=dict(size=7)))
        rv = 100 * float(getattr(self.human_ufun, "reserved_value", 0) or 0)
        if y == "human":
            fig.add_hline(y=rv, line_dash="dot", line_color="#ef4444", annotation_text="Disagreement",
                          annotation_position="bottom right")
        fig.update_layout(**base_layout(280, xaxis_title=(time_cols | ycols)[x], yaxis_title=ycols[y],
                                        yaxis=dict(range=[0, 102], ticksuffix="%")))
        if x == "relative_time":
            fig.update_xaxes(range=[0, 1])
        elif x == "step" and m.nmi.n_steps:
            fig.update_xaxes(range=[0, m.nmi.n_steps])
        xopts = time_cols | ({"agent": "Agent utility"} if show_agent else {})
        controls = [ui.select("x", {v: k for k, v in xopts.items()}, x, label="X axis"),
                    ui.select("y", {v: k for k, v in ycols.items()}, y, label="Y axis")]
        if self.is_admin:
            controls.append(ui.checkbox("show_agent", show_agent, label="Show agent utility"))
        return [ui.row(*controls, align="end"), ui.plot(fig)]


class OutcomePlotTool(Tool):
    name = "Outcome Plot"
    description = "Offers placed in the outcome space (any two issues or time)."
    icon = "scatter-chart"
    pane = "lower"
    timing = "start"
    enabled = False
    order = 11

    def view(self):
        m = self.mechanism
        if m is None:
            return [ui.text_block("Starts with the negotiation.", muted=True)]
        human_id = self.session_state.get("human_id")
        names = [i.name for i in self.issues]
        cols = names + ["relative_time", "step"]
        x = self.values.get("x", names[0] if names else "step")
        y = self.values.get("y", names[1] if len(names) > 1 else "step")
        x = x if x in cols else cols[0]
        y = y if y in cols else cols[min(1, len(cols) - 1)]
        show_human = self.values.get("show_human", True)
        df = trace_frame(self.trace(), self.issues)
        fig = go.Figure()
        for neg in (df["negotiator"].unique() if len(df) else []):
            if not show_human and str(neg) == str(human_id):
                continue
            sub = df[df["negotiator"] == neg]
            fig.add_trace(go.Scatter(x=sub[x], y=sub[y], mode="lines+markers",
                                     name="You" if str(neg) == str(human_id) else "Partner",
                                     line=dict(color=party_color(neg, human_id)), marker=dict(size=8)))
        for col, axis in ((x, "xaxis"), (y, "yaxis")):
            issue = next((i for i in self.issues if i.name == col), None)
            if issue is not None and not issue.is_numeric():
                fig.update_layout(**{axis: dict(type="category", categoryarray=[str(v) for v in issue.all])})
        fig.update_layout(**base_layout(300, xaxis_title=x, yaxis_title=y))
        return [
            ui.row(ui.select("x", cols, x, label="X axis"), ui.select("y", cols, y, label="Y axis"),
                   ui.checkbox("show_human", show_human, label="Show your offers"), align="end"),
            ui.plot(fig),
        ]


class TraceTool(Tool):
    name = "Trace"
    description = "A table of every offer with its utility."
    icon = "list"
    pane = "lower"
    timing = "start"
    enabled = False
    order = 12

    def view(self):
        human_id = self.session_state.get("human_id")
        show_agent = bool(self.values.get("show_agent", False)) and self.is_admin
        rows = []
        for r in self.trace():
            t, rel, step, neg, offer = (list(r) + [None] * 9)[:5]
            text = (list(r) + [None] * 9)[7]
            row = {"Step": step, "Time": rel, "By": "You" if str(neg) == str(human_id) else "Partner",
                   "Offer": self.session.outcome_str(offer) if offer is not None else "—",
                   "Message": text or "",
                   "Your utility": float(self.human_ufun(offer)) if offer is not None else None}
            if show_agent:
                row["Agent utility"] = float(self.agent_ufun(offer)) if offer is not None else None
            rows.append(row)
        comps: list[ui.Component] = []
        if self.is_admin:
            comps.append(ui.checkbox("show_agent", show_agent, label="Show agent utility"))
        comps.append(ui.table(rows, formats={"Time": "percent", "Your utility": "percent", "Agent utility": "percent"},
                              page_size=50))
        return comps


class ValueHistogramTool(Tool):
    name = "Value Histogram"
    description = "How often each value of each issue has been offered."
    icon = "chart-column"
    pane = "lower"
    timing = "start"
    order = 5

    def view(self):
        if self.mechanism is None:
            return [ui.text_block("Starts with the negotiation.", muted=True)]
        human_id = self.session_state.get("human_id")
        names = [i.name for i in self.issues]
        selected = [n for n in self.values.get("issues", names[:1]) if n in names] or names[:1]
        show_human = self.values.get("show_human", True)
        two = self.values.get("two_cols", False)
        df = trace_frame(self.trace(), self.issues)
        if not show_human and len(df):
            df = df[df["negotiator"] != human_id]
        plots = []
        for issue in self.issues:
            if issue.name not in selected:
                continue
            fig = go.Figure()
            if issue.is_discrete() and issue.cardinality <= 25:
                allv = list(issue.all)
                for neg in (df["negotiator"].unique() if len(df) else []):
                    counts = df[df["negotiator"] == neg][issue.name].value_counts()
                    fig.add_trace(go.Bar(x=[str(v) for v in allv], y=[int(counts.get(v, 0)) for v in allv],
                                         name="You" if str(neg) == str(human_id) else "Partner",
                                         marker_color=party_color(neg, human_id), opacity=0.85))
                fig.update_layout(xaxis=dict(type="category"), barmode="group")
            else:
                for neg in (df["negotiator"].unique() if len(df) else []):
                    fig.add_trace(go.Histogram(x=df[df["negotiator"] == neg][issue.name], nbinsx=20,
                                               name="You" if str(neg) == str(human_id) else "Partner",
                                               marker_color=party_color(neg, human_id), opacity=0.75))
                fig.update_layout(barmode="overlay")
            fig.update_layout(**base_layout(220, yaxis_title="count", xaxis_title=issue.name))
            plots.append(ui.plot(fig))
        return [
            ui.row(ui.multiselect("issues", names, selected, label="Issues"),
                   ui.checkbox("show_human", show_human, label="Your offers"),
                   ui.checkbox("two_cols", two, label="Two columns"), align="end"),
            ui.grid(*plots, cols=2 if two else 1) if plots else ui.text_block("Select an issue.", muted=True),
        ]


# --------------------------------------------------------------------------- #
# Results                                                                      #
# --------------------------------------------------------------------------- #
def _results_view(tool: Tool, df, *, leaderboard: bool) -> list[ui.Component]:
    from hani2.results import DEFAULT_COLUMNS, scenario_scores
    from hani2.results import leaderboard as make_lb

    if df is None or len(df) == 0:
        return [ui.text_block("No negotiations yet.", muted=True)]
    score, per = scenario_scores(df)
    comps: list[ui.Component] = [
        ui.stats(
            ui.stat("Score", f"{score:.1f}", hint="Average of your best results per scenario"),
            ui.stat("Negotiations", len(df)),
            ui.stat("Agreements", int((df.get("status") == "success").sum()) if "status" in df else "—"),
        )
    ]
    if per:
        comps.append(ui.table([{"Scenario": s, "Score": 100 * v, "Negotiations": n} for s, (v, n) in per.items()],
                              formats={"Score": "float"}, sortable=True))
    if leaderboard:
        lb = make_lb(df)
        if lb:
            comps.append(ui.card(ui.table([{"User": r["user"], "Score": r["score"], "Negotiations": r["negotiations"]}
                                           for r in lb], formats={"Score": "float"}), title="Leaderboard"))
    all_cols = [str(c) for c in df.columns]
    default_cols = [c for c in DEFAULT_COLUMNS + (["user"] if leaderboard else []) if c in all_cols]
    cols = [c for c in tool.values.get("columns", default_cols) if c in all_cols] or default_cols
    comps.append(ui.multiselect("columns", all_cols, cols, label="Columns"))
    comps.append(ui.table(df[cols].iloc[::-1], formats={"human_utility": "percent", "agent_utility": "percent",
                                                       "human_advantage": "percent", "nash_optimality": "float"},
                          searchable=True))
    return comps


class UserResultsTool(Tool):
    name = "My Results"
    description = "Your score and every negotiation you completed."
    icon = "trophy"
    pane = "upper"
    timing = "always"
    permanent = True
    guest = False
    order = 30

    def negotiation_ended(self, session_state, nmi):
        self.refresh()

    def view(self):
        from hani2.results import read_user_results

        return _results_view(self, read_user_results(self.session_state["user"]), leaderboard=False)


class AllResultsTool(Tool):
    name = "All Results"
    description = "Every participant's results and a leaderboard (admins only)."
    icon = "table"
    pane = "upper"
    timing = "always"
    admin_only = True
    order = 60

    def view(self):
        from hani2.results import read_all_results

        return _results_view(self, read_all_results(), leaderboard=True)


# --------------------------------------------------------------------------- #
# Outcome selectors                                                            #
# --------------------------------------------------------------------------- #
class UtilitySelectorTool(OutcomeSelector):
    name = "Utility-based Selector"
    description = "Browse every outcome whose utility for you is in a chosen range and use one as your offer."
    icon = "list-filter"
    pane = "side"
    timing = "start"
    order = 0

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._inverter = None
        self.values.update(min_util=70, width=10)

    def negotiation_started(self, session_state, nmi):
        self._inverter = None
        super().negotiation_started(session_state, nmi)

    def _get_inverter(self):
        if self._inverter is None:
            ufun = self.human_ufun
            self._inverter = self._cached(ufun) or ufun.invert()
        return self._inverter

    def _cached(self, ufun):
        sdir = self.session_state.get("scenario_dir")
        if not sdir:
            return None
        path = Path(sdir) / f"inverter_h{self.human_index}.pkl"
        if not path.is_file():
            return None
        try:
            with path.open("rb") as fh:
                inv = pickle.load(fh)
            cached = getattr(inv, "ufun", None)
            sample = list(ufun.outcome_space.enumerate_or_sample(max_cardinality=16))
            if cached is None or not all(abs(float(ufun(o)) - float(cached(o))) <= 1e-6 for o in sample):
                return None
            return inv
        except Exception:
            return None

    def _range(self):
        lo = float(self.values.get("min_util", 70)) / 100
        return lo, min(1.0, lo + float(self.values.get("width", 10)) / 100)

    def _outcomes(self) -> list:
        if self.human_ufun is None:
            return []
        try:
            return list(self._get_inverter().some(self._range(), normalized=True))
        except Exception:
            return []

    def selector_view(self):
        rows = []
        for o in self._outcomes()[:500]:
            d = self.outcome_dict(o) or {}
            d["Utility"] = float(self.human_ufun(o))
            rows.append(d)
        rows.sort(key=lambda r: -r["Utility"])
        sel = self.values.get("selected")
        return [
            ui.slider("min_util", 0, 100, self.values.get("min_util", 70), label="Minimum utility", suffix="%"),
            ui.slider("width", 1, 100, self.values.get("width", 10), label="Range width", suffix="%"),
            ui.table(rows, on_select="pick", formats={"Utility": "percent"}, page_size=15, selected=sel,
                     max_height=320)
            if rows
            else ui.alert("No outcome in this utility range.", "neutral"),
        ]

    def on_input(self, name, value):
        self.values["selected"] = None
        super().on_input(name, value)

    def on_action(self, action, payload):
        if action == "pick":
            row = payload.get("row") or {}
            self.values["selected"] = payload.get("index")
            self.set_offer({k: v for k, v in row.items() if k != "Utility"})
            self.refresh()
            return
        super().on_action(action, payload)

    def get_outcome(self) -> Outcome | None:
        try:
            return self._get_inverter().one_in(self._range(), normalized=True)
        except Exception:
            return None


class RandomOutcomeTool(OutcomeSelector):
    name = "Random"
    description = "Fill the offer with a random outcome (admins only)."
    icon = "dices"
    admin_only = True
    order = 20

    def selector_view(self):
        return [ui.markdown("Samples a random outcome and puts it in your offer.")]

    def get_outcome(self):
        s = self.scenario
        if s is None:
            return None
        try:
            return s.outcome_space.random_outcome()
        except Exception:
            return random.choice(list(s.outcome_space.enumerate_or_sample(max_cardinality=1000)))


class ResponseGeneratorTool(OutcomeSelector):
    name = "LLM"
    description = "Describe what you want in plain words and let an LLM write the offer and message."
    icon = "sparkles"
    admin_only = True
    order = 10

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.values.update(instruction="", mode="both")
        self.generated: dict[str, Any] | None = None
        self.status = ""
        self.busy = False

    def negotiation_started(self, session_state, nmi):
        self.generated = None
        self.status = ""
        super().negotiation_started(session_state, nmi)

    def view(self):
        from hani2.llm_service import get_llm_status

        st = get_llm_status()
        comps: list[ui.Component] = []
        if not st.get("configured"):
            comps.append(ui.alert(f"The LLM is not configured (provider `{st.get('provider')}`).", "warning"))
        comps += [
            ui.textarea("instruction", self.values.get("instruction", ""), rows=3,
                        placeholder="e.g. Propose a fair middle ground, or: improve my last offer slightly"),
            ui.radio("mode", {"Text & offer": "both", "Text only": "text_only", "Offer only": "outcome_only"},
                     self.values.get("mode", "both")),
            ui.button("Generating…" if self.busy else "Generate", "generate", variant="primary", icon="sparkles",
                      disabled=self.busy or not self.can_set(), full=True),
        ]
        if self.status:
            comps.append(ui.alert(self.status, "error" if self.status.startswith("Error") else "info"))
        g = self.generated
        if g:
            if g.get("outcome"):
                comps.append(ui.outcome(g["outcome"], g.get("utility"), label="Suggested offer"))
            if g.get("text"):
                comps.append(ui.card(ui.markdown(g["text"]), title="Suggested message"))
            comps.append(ui.button("Apply to my offer", "apply", variant="success", icon="arrow-left-to-line", full=True))
        return comps

    def on_input(self, name, value):
        self.values[name] = value  # no re-render while typing

    def on_action(self, action, payload):
        if action == "generate":
            if payload.get("instruction") is not None:
                self.values["instruction"] = payload["instruction"]
            self.busy, self.status = True, ""
            self.refresh()
            self.session.submit(self._generate)
        elif action == "apply" and self.generated:
            if self.generated.get("outcome"):
                self.set_offer(self.generated["outcome"])
            if self.generated.get("text"):
                self.set_text(self.generated["text"])
            self.toast("Applied to your offer", "success")

    def _generate(self):
        from hani2.llm_service import generate_from_instruction

        try:
            instr = (self.values.get("instruction") or "").strip()
            if not instr:
                self.status = "Error: write an instruction first."
                return
            res = generate_from_instruction(instruction=instr, issues=self.issues, context=self.session.llm_context(),
                                            output_mode=self.values.get("mode", "both"))
            if res.error:
                self.status = f"Error: {res.error}"
                return
            out = self.outcome_dict(res.outcome) if res.outcome is not None else None
            self.generated = {"outcome": out, "text": res.text,
                              "utility": self.session.utility(res.outcome) if res.outcome is not None else None}
            self.status = ""
        except Exception as e:  # noqa: BLE001
            self.status = f"Error: {e}"
        finally:
            self.busy = False
            self.refresh()
