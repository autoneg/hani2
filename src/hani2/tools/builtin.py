"""The built-in tools."""

from __future__ import annotations

import pickle
import random
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
from negmas import Outcome

from hani2.tools import ui
from hani2.tools.base import OutcomeSelector, Tool
from hani2.tools.ufun_views import PREFERENCES_HELP_MD, render_ufun_view  # noqa: F401
from hani2.tools.plotting import (
    AGENT_COLOR,
    HUMAN_COLOR,
    base_layout,
    party_color,
    trace_frame,
)

__all__ = [
    "PreferencesTool",
    "OpponentPreferencesTool",
    "AgentPreferencesTool",
    "ScenarioInfoTool",
    "UtilityPlotTool",
    "NegotiationPlotTool",
    "OutcomePlotTool",
    "TraceTool",
    "ValueHistogramTool",
    "UserResultsTool",
    "AllResultsTool",
    "UtilitySelectorTool",
    "RandomOutcomeTool",
    "ResponseGeneratorTool",
]

# --------------------------------------------------------------------------- #
# Preferences                                                                  #
# --------------------------------------------------------------------------- #
def preference_view(tool: Tool, ufun, *, title_prefix: str = "", help_card: bool = True) -> list[ui.Component]:
    """The preferences of ``ufun``, rendered by the view registered for its type (see :mod:`hani2.tools.ufun_views`)."""
    return render_ufun_view(tool, ufun, title_prefix=title_prefix, help_card=help_card)


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


class OpponentPreferencesTool(Tool):
    name = "Opponent Preferences"
    description = "The opponent's private preferences (admins only)."
    icon = "bot"
    pane = "upper"
    timing = "load"
    admin_only = True
    order = 50

    def view(self):
        return [ui.alert("Only visible to administrators.", "warning"),
                *preference_view(self, self.agent_ufun, title_prefix="Opponent ", help_card=False)]


#: Former name, kept so existing imports keep working.
AgentPreferencesTool = OpponentPreferencesTool


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
        descs = {(role if str(k).lower() == role.lower() else k): v for k, v in descs.items()}
        rows = []
        for issue in s.outcome_space.issues:
            d = descs.get(role, {}).get(issue.name, "") if isinstance(descs.get(role), dict) else descs.get(issue.name, "")
            vals = (f"{issue.min_value} – {issue.max_value}" if issue.is_continuous() or issue.cardinality > 12
                    else ", ".join(str(v) for v in issue.all))
            rows.append({"Issue": issue.name, "Options": vals, "Description": d or ""})
        comps: list[ui.Component] = [
            ui.heading(info.get("title") or str(s.outcome_space.name), 3),
            *([] if getattr(self.session, "labels", None) and role.strip().lower() in self.session.labels
              else [ui.row(ui.badge(f"You act as {role}", "primary"))]),
        ]
        shown = getattr(self.session, "relabel_text", lambda t: t)
        if info.get("short_description"):
            comps.append(ui.markdown(shown(info["short_description"])))
        for r in rows:
            r["Options"] = shown(r["Options"])
            r["Description"] = shown(r["Description"])
        comps.append(ui.table(rows, ["Issue", "Options", "Description"], sortable=False, page_size=50))
        hints_all = info.get("hints") or {}
        hints = next((v for k, v in hints_all.items() if str(k).lower() == role.lower()), None) or {}
        if hints:
            comps.append(ui.kv({shown(str(k)): shown(str(v)) for k, v in hints.items()}, title="Hints"))
        if info.get("long_description"):
            comps.append(ui.card(ui.markdown(shown(info["long_description"]), size="sm"), title="Full description",
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
        show_agent = bool(self.values.get("show_agent", False)) and self.may_see_opponent
        time_cols = {"relative_time": "Relative time", "step": "Step", "time": "Time (s)"}
        ycols = {"human": "Your utility"} | ({"agent": "Opponent utility"} if show_agent else {})
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
            fig.add_hline(y=rv, line_dash="dot", line_color="#ef4444", annotation_text="No deal",
                          annotation_position="top left")
        fig.update_layout(**base_layout(280, xaxis_title=(time_cols | ycols)[x], yaxis_title=ycols[y],
                                        yaxis=dict(range=[0, 102], ticksuffix="%")))
        if x == "relative_time":
            fig.update_xaxes(range=[0, 1])
        elif x == "step" and m.nmi.n_steps:
            fig.update_xaxes(range=[0, m.nmi.n_steps])
        xopts = time_cols | ({"agent": "Opponent utility"} if show_agent else {})
        controls = [ui.select("x", {v: k for k, v in xopts.items()}, x, label="X axis"),
                    ui.select("y", {v: k for k, v in ycols.items()}, y, label="Y axis")]
        if self.may_see_opponent:
            controls.append(ui.checkbox("show_agent", show_agent, label="Show opponent utility"))
        return [ui.row(*controls, align="end"), ui.plot(fig)]


class NegotiationPlotTool(Tool):
    """The negotiation in utility space: every outcome placed by its utility for
    you (x) and for the opponent (y), with the Pareto frontier, Nash and Kalai
    points, both no-deal values, the offer trajectories and the agreement."""

    name = "Negotiation Plot"
    description = "All outcomes in utility space with the Pareto frontier, Nash point and both sides' offers."
    icon = "chart-scatter"
    pane = "lower"
    timing = "load"
    admin_only = True
    order = 9
    max_points = 4000

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.values.update(show_outcomes=True, show_pareto=True, show_points=True)
        self._cache_key = None
        self._cache: dict = {}

    def _space(self):
        s = self.scenario
        if s is None:
            return None
        key = id(s)
        if self._cache_key != key:
            from negmas.preferences.ops import kalai_points, nash_points, pareto_frontier

            ufuns = (self.human_ufun, self.agent_ufun)
            outcomes = list(s.outcome_space.enumerate_or_sample(max_cardinality=self.max_points))
            pts = [(float(ufuns[0](o)), float(ufuns[1](o))) for o in outcomes]
            try:
                frontier, idx = pareto_frontier(ufuns, outcomes=outcomes, sort_by_welfare=True)
                frontier = sorted((float(a), float(b)) for a, b in frontier)
                nash = [(float(p[0][0]), float(p[0][1])) for p in nash_points(ufuns, frontier=frontier, outcome_space=s.outcome_space)]
                kalai = [(float(p[0][0]), float(p[0][1])) for p in kalai_points(ufuns, frontier=frontier, outcome_space=s.outcome_space)]
            except Exception:  # pragma: no cover - continuous / odd spaces
                frontier, nash, kalai = [], [], []
            self._cache = dict(points=pts, outcomes=outcomes, frontier=frontier, nash=nash, kalai=kalai)
            self._cache_key = key
        return self._cache

    def view(self):
        sp = self._space()
        if sp is None:
            return [ui.text_block("Load a scenario first.", muted=True)]
        hu, au = self.human_ufun, self.agent_ufun
        human_id = self.session_state.get("human_id")
        fig = go.Figure()
        if self.values.get("show_outcomes", True):
            labels = [self.session.outcome_str(o) for o in sp["outcomes"]]
            fig.add_trace(go.Scattergl(x=[p[0] for p in sp["points"]], y=[p[1] for p in sp["points"]], mode="markers",
                                       name="Outcomes", marker=dict(size=5, color="rgba(100,116,139,0.35)"),
                                       text=labels, hovertemplate="%{text}<br>you %{x:.0%} · opponent %{y:.0%}<extra></extra>"))
        if self.values.get("show_pareto", True) and sp["frontier"]:
            fig.add_trace(go.Scatter(x=[p[0] for p in sp["frontier"]], y=[p[1] for p in sp["frontier"]], mode="lines+markers",
                                     name="Pareto frontier", line=dict(color="#10b981", width=2), marker=dict(size=6)))
        if self.values.get("show_points", True):
            for pts, label, symbol in ((sp["nash"], "Nash", "star"), (sp["kalai"], "Kalai", "diamond")):
                if pts:
                    fig.add_trace(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="markers", name=label,
                                             marker=dict(size=14, symbol=symbol, color="#a855f7", line=dict(width=1, color="white"))))
        for neg_is_human, color, label in ((True, HUMAN_COLOR, "Your offers"), (False, AGENT_COLOR, "Opponent offers")):
            rows = [r for r in self.trace() if (str(r[3]) == str(human_id)) == neg_is_human and r[4] is not None]
            if rows:
                fig.add_trace(go.Scatter(
                    x=[float(hu(r[4])) for r in rows], y=[float(au(r[4])) for r in rows], mode="lines+markers", name=label,
                    line=dict(color=color, width=2), marker=dict(size=8, color=color),
                    text=[f"round {r[2] + 1}: {self.session.outcome_str(r[4])}" for r in rows],
                    hovertemplate="%{text}<br>you %{x:.0%} · opponent %{y:.0%}<extra></extra>"))
        m = self.mechanism
        agreement = getattr(getattr(m, "state", None), "agreement", None) if m is not None else None
        if agreement is not None:
            fig.add_trace(go.Scatter(x=[float(hu(agreement))], y=[float(au(agreement))], mode="markers", name="Agreement",
                                     marker=dict(size=18, symbol="circle-open", color="#ef4444", line=dict(width=3))))
        for v, axis in ((float(hu.reserved_value or 0), "x"), (float(au.reserved_value or 0), "y")):
            (fig.add_vline if axis == "x" else fig.add_hline)(v, line_dash="dot", line_color="#ef4444", opacity=0.6)
        fig.update_layout(**base_layout(380, xaxis=dict(title="Your utility", range=[0, 1.02], tickformat=".0%"),
                                        yaxis=dict(title="Opponent utility", range=[0, 1.02], tickformat=".0%")))
        return [
            ui.row(ui.checkbox("show_outcomes", self.values.get("show_outcomes", True), label="All outcomes"),
                   ui.checkbox("show_pareto", self.values.get("show_pareto", True), label="Pareto frontier"),
                   ui.checkbox("show_points", self.values.get("show_points", True), label="Nash / Kalai")),
            ui.plot(fig),
            ui.text_block("Dotted lines: each side's value on disagreement.", muted=True),
        ]


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
        show_agent = bool(self.values.get("show_agent", False)) and self.may_see_opponent
        rows = []
        for r in self.trace():
            t, rel, step, neg, offer = (list(r) + [None] * 9)[:5]
            text = (list(r) + [None] * 9)[7]
            row = {"Step": step, "Time": rel, "By": "You" if str(neg) == str(human_id) else "Partner",
                   "Offer": self.session.outcome_str(offer) if offer is not None else "—",
                   "Message": text or "",
                   "Your utility": float(self.human_ufun(offer)) if offer is not None else None}
            if show_agent:
                row["Opponent utility"] = float(self.agent_ufun(offer)) if offer is not None else None
            rows.append(row)
        comps: list[ui.Component] = []
        if self.may_see_opponent:
            comps.append(ui.checkbox("show_agent", show_agent, label="Show opponent utility"))
        comps.append(ui.table(rows, formats={"Time": "percent", "Your utility": "percent", "Opponent utility": "percent"},
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
