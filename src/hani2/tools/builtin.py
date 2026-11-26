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
    "UtilityBarTool",
    "UtilitySelectorTool",
    "RandomOutcomeTool",
    "ResponseGeneratorTool",
]

# --------------------------------------------------------------------------- #
# Preferences                                                                  #
# --------------------------------------------------------------------------- #
def _viewer_role(tool: Tool) -> str:
    return str(tool.session_state.get("human_id", "")).replace(" (You)", "")


def _may_see_hints(tool: Tool) -> bool:
    """Hints are drawn from the preferences: only a viewer who knows all of them sees them."""
    sess = tool.session_state.get("_session")
    if sess is None:
        return True
    st = tool.information
    viewer = sess.current_viewer() if hasattr(sess, "current_viewer") else "human"
    return (st.assistant_prefs if viewer == "assistant" else st.human_prefs) == "full"


def role_hints(tool: Tool) -> dict[str, str]:
    """The scenario's hints for the participant's role, relabelled for display
    (empty when the viewer may not see them)."""
    s = tool.scenario
    if s is None or not _may_see_hints(tool):
        return {}
    role = _viewer_role(tool)
    hints_all = (s.info or {}).get("hints") or {}
    hints = next((v for k, v in hints_all.items() if str(k).lower() == role.lower()), None) or {}
    shown = getattr(tool.session, "relabel_text", lambda t: t)
    return {shown(str(k)): shown(str(v)) for k, v in hints.items()} if isinstance(hints, dict) else {}


def _help_split(comps: list[ui.Component]) -> tuple[list[ui.Component], list[ui.Component]]:
    """The view's components and its trailing (collapsed) help card."""
    if comps and comps[-1].get("type") == "card" and comps[-1].get("title") == "How your preferences work":
        return comps[:-1], comps[-1:]
    return comps, []


def preference_view(tool: Tool, ufun, *, title_prefix: str = "", help_card: bool = True) -> list[ui.Component]:
    """The preferences of ``ufun``, rendered by the view registered for its type (see :mod:`hani2.tools.ufun_views`)."""
    return render_ufun_view(tool, ufun, title_prefix=title_prefix, help_card=help_card)


class PreferencesTool(Tool):
    name = "Preferences"
    groups = ("information",)
    description = "Your issue weights, the value of every option and your value on disagreement."
    help = """
    **What it shows.** How much every possible deal is worth to *you*, from 0% (worst) to 100% (best).

    - **In short**: your preferences in two or three sentences (always shown).
    - **Issue weights** (donut): how important each issue is; the weights add up to 100%.
    - **Value of each option** (bars): pick an issue to see what each of its options is worth to you.
    - **Value on disagreement**: one sentence under the charts, e.g. "If you do not reach agreement
      you get 10% (your best option gives you 100%)".
    - **Hints**: the hints of your role and, for every issue, what you want in plain words
      ("the lower, the better", "best at 5 days").

    **How it works.** A deal's value is the weighted sum of its options' values:
    weight₁ × value₁ + weight₂ × value₂ + … A deal worth less than your value on
    disagreement is worse than no deal. Open *How your preferences work* at the bottom
    for a worked example. This tool is always on.
    """
    icon = "sliders-horizontal"
    pane = "upper"
    timing = "load"
    permanent = True
    order = 1
    private_information = True

    def private_now(self) -> bool:
        """Private only when it shows something the Assistant does not know itself."""
        st = self.information
        a, h = st.assistant_prefs, st.human_prefs
        covered = a == "full" or a == h or h == "none"
        return not covered or (st.human_sees_reserved and not st.assistant_sees_reserved)

    def view(self):
        st = self.information
        rv_hint = None
        if not st.human_sees_reserved:
            rv_hint = "You do not know it; your Assistant does" if st.assistant_sees_reserved else "You do not know it"
        if st.human_prefs == "full":
            return self._full_view(rv_hint)
        from hani2.tools.ufun_views import partial_preference_view

        holder = "your Assistant" if st.assistant_prefs != "none" else "nobody"
        return partial_preference_view(self, self.human_ufun, st.human_prefs, reserved_hint=rv_hint, other_holder=holder)


    def _full_view(self, rv_hint: str | None) -> list[ui.Component]:
        from hani2.tools.ufun_views import issue_explanations, preference_summary

        ufun = self.human_ufun
        comps = render_ufun_view(self, ufun, reserved_hint=rv_hint)
        if ufun is None:
            return comps
        body, help_ = _help_split(comps)
        out: list[ui.Component] = []
        summary = _safe(lambda: preference_summary(ufun))
        if summary:
            out.append(ui.card(ui.markdown(summary, size="sm"), title="In short"))
        out += body
        hints = role_hints(self)
        s = self.scenario
        lines = _safe(lambda: issue_explanations(
            ufun, (s.info if s is not None else None) or {},
            roles=[str(u.name) for u in (s.ufuns if s is not None else ())])) or []
        if not _may_see_hints(self):
            lines = []
        shown = getattr(self.session, "relabel_text", lambda t: t)
        if hints or lines:
            parts = []
            if hints:
                parts.append(ui.kv(hints))
            if lines:
                parts.append(ui.kv([(shown(n), shown(t)) for n, t in lines], title="What you want on each issue"))
            out.append(ui.card(*parts, title="Hints"))
        return out + help_


def _safe(fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001 - a hint must never break the view
        import traceback

        traceback.print_exc()
        return None


class OpponentPreferencesTool(Tool):
    name = "Opponent Preferences"
    groups = ("information",)
    description = "The opponent's private preferences (admins only)."
    help = """
    **What it shows.** The same charts as *Preferences*, for the opponent: its issue
    weights, the value it gives each option and its value on disagreement.

    **How it works.** Read straight from the opponent's utility function in the scenario.
    Participants never get this tool unless an administrator opens it to them.
    """
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
#: How the Scenario Info tool shows the picture (label → value).
PICTURE_STYLES = {"Small": "small", "Large": "large", "Watermark": "watermark"}
PICTURE_STYLE_NAMES = set(PICTURE_STYLES.values())


class ScenarioInfoTool(Tool):
    def _may_see_hints(self) -> bool:
        return _may_see_hints(self)

    name = "Scenario Info"
    groups = ("information",)
    description = "The scenario description, the issues and hints for your role."
    help = """
    **What it shows.** A picture of the scenario (switch it off with *Picture*, or in your
    settings; *Small* shows it beside the story, *Large* above it, *Watermark* faintly
    behind it), the
    story of the scenario, the role you play, a table of the issues with their possible
    options and what they mean, any hints for your role and (collapsed at the bottom) the
    full description.

    **How it works.** Everything comes from the scenario's description; nothing here
    changes during the negotiation. This tool is always on.
    """
    icon = "book-open"
    pane = "upper"
    timing = "load"
    permanent = True
    order = 0  # the first tab of the tools: read the scenario, then your preferences

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
            fmt = (info.get("issue_format") or {}).get(issue.name, "{}")

            def _f(v, fmt=fmt):
                try:
                    return fmt.format(v)
                except (ValueError, TypeError, IndexError):
                    return str(v)

            vals = (f"{_f(issue.min_value)} – {_f(issue.max_value)}" if issue.is_continuous() or issue.cardinality > 12
                    else ", ".join(_f(v) for v in issue.all))
            rows.append({"Issue": issue.name, "Options": vals, "Description": d or ""})
        title = info.get("title") or str(s.outcome_space.name)
        badge = ([] if getattr(self.session, "labels", None) and role.strip().lower() in self.session.labels
                 else [ui.badge(f"You act as {role}", "primary")])
        light, dark = self._picture()
        prefs = getattr(self.session, "prefs", None) or {}
        show = bool(prefs.get("show_scenario_picture", True))
        style = self._picture_style(info, prefs)
        may = getattr(self.session, "may_adjust", lambda k: True)
        controls = [ui.switch("show_picture", show, label="Picture")] if light and may("show_scenario_picture") else []
        if light and show and may("scenario_picture_style"):
            controls.append(ui.select("picture_style", PICTURE_STYLES, style))
        comps: list[ui.Component] = [ui.heading(title, 3)]
        if badge or controls:
            comps.append(ui.row(*badge, *controls, align="center"))
        shown = getattr(self.session, "relabel_text", lambda t: t)
        story = ui.markdown(shown(info["short_description"])) if info.get("short_description") else None
        for r in rows:
            r["Options"] = shown(r["Options"])
            r["Description"] = shown(r["Description"])
        table = ui.table(rows, ["Issue", "Options", "Description"], sortable=False, page_size=50)
        if light and show:
            if style == "large":
                comps.append(ui.image(light, dark_src=dark, alt=self._picture_alt(title), max_height=240))
                comps.extend(c for c in (story, table) if c)
            elif style == "watermark":  # behind the story (or the issues when there is none)
                pic = ui.image(light, dark_src=dark, alt=self._picture_alt(title))
                comps.append(ui.figure(pic, story or table, placement="watermark"))
                if story:
                    comps.append(table)
            else:  # small: beside the story
                pic = ui.image(light, dark_src=dark, alt=self._picture_alt(title), max_height=120)
                comps.append(ui.figure(pic, story, placement="side"))
                comps.append(table)
        else:
            comps.extend(c for c in (story, table) if c)
        hints = role_hints(self)  # empty when this viewer knows only part of the preferences
        if hints:
            comps.append(ui.kv(hints, title="Hints"))
        if info.get("long_description"):
            opened = bool(prefs.get("open_scenario_description", False))
            loaded = self.session_state.get("load_at_dt")
            card = ui.card(ui.markdown(shown(info["long_description"]), size="sm"), title="Full description",
                           collapsible=True, collapsed=not opened)
            # a new id for every loaded scenario (and setting value), so it starts opened or closed as set
            card["id"] = f"scenario-description-{loaded.timestamp() if loaded else 0}-{int(opened)}"
            comps.append(card)
        return comps

    def on_input(self, name: str, value: Any) -> None:
        prefs = {"show_picture": ("show_scenario_picture", bool),
                 "picture_style": ("scenario_picture_style", lambda v: str(v).lower())}
        if name in prefs:  # the participant's own settings (refused when the admin does not allow them)
            key, conv = prefs[name]
            setter = getattr(self.session, "set_pref", None)
            if setter is None or not setter(key, conv(value)):
                self.refresh()  # refused: show the control as it was
            return
        super().on_input(name, value)

    def _picture(self) -> tuple[str | None, str | None]:
        """``(light, dark)`` picture URLs of the loaded scenario, looked up once per scenario."""
        from hani2 import scenario_pictures

        s = self.scenario
        sdir = self.session_state.get("scenario_dir")
        stype = (self.session_state.get("scenario_info") or {}).get("scenario_type")
        key = (id(s), sdir, stype)
        cached = self.__dict__.get("_picture_cache")
        if cached is None or cached[0] != key:
            try:
                found = scenario_pictures.sources(sdir, stype, (s.info or {}) if s is not None else None)
            except Exception as e:  # noqa: BLE001 - a broken picture must not hide the scenario
                print(f"[hani2] scenario picture: {e!r}")
                found = (None, None)
            cached = (key, found)
            self.__dict__["_picture_cache"] = cached
        return cached[1]

    def _picture_style(self, info: dict, prefs: dict) -> str:
        """``small`` (beside the story), ``large`` (above it) or ``watermark`` (behind it):
        the ``scenario_picture_style`` setting (the participant's, else the layered default),
        else the scenario's ``picture_style``, else ``small``."""
        for v in (prefs.get("scenario_picture_style"), info.get("picture_style")):
            if str(v or "").lower() in PICTURE_STYLE_NAMES:
                return str(v).lower()
        return "small"

    def _picture_alt(self, title: str) -> str:
        info = (self.scenario.info if self.scenario is not None else None) or {}
        return str(info.get("picture_alt") or title)


# --------------------------------------------------------------------------- #
# Plots                                                                        #
# --------------------------------------------------------------------------- #
class UtilityPlotTool(Tool):
    needs_totals = True
    name = "Utility Plot"
    groups = ("visualization",)
    description = "How the utility of the offers evolves over time."
    help = """
    **What it shows.** A line chart of every offer so far: by default the round on the
    x axis and the offer's value *for you* on the y axis, one line for your offers and one
    for your opponent's. The dotted red line is your value on disagreement.

    **How to use it.** Choose the axes with the two drop-downs (relative time, round or
    seconds). An opponent line that rises means the opponent is conceding towards you; a flat
    line means it is holding firm. It is off by default: switch it on to use it.
    """
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
                    mode="lines+markers", name="You" if str(neg) == str(human_id) else "Opponent",
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


class _Normalized:
    """A utility function scaled to 0..1 over the outcome space (for drawing an estimate, which
    may come in any scale), with its reserved value scaled the same way."""

    def __init__(self, ufun, outcomes):
        self.ufun = ufun
        vals = [float(ufun(o)) for o in outcomes] or [0.0, 1.0]
        self.lo, self.hi = min(vals), max(vals)
        self.reserved_value = self._scale(float(getattr(ufun, "reserved_value", 0.0) or 0.0))

    def _scale(self, u: float) -> float:
        return (u - self.lo) / (self.hi - self.lo) if self.hi - self.lo > 1e-12 else 1.0

    def __call__(self, o) -> float:
        return self._scale(float(self.ufun(o)))

    def minmax(self, *a, **kw) -> tuple[float, float]:
        return 0.0, 1.0


def opponent_estimate(tool: Tool):
    """The session's estimate of the opponent's utility function, or ``None``."""
    try:
        return tool.session.opponent_ufun_estimate
    except Exception:  # noqa: BLE001
        return None


class NegotiationPlotTool(Tool):
    needs_totals = True
    """The negotiation in utility space: every outcome placed by its utility for
    you (x) and for the opponent (y), with the Pareto frontier, Nash and Kalai
    points, both no-deal values, the offer trajectories and the agreement.

    The opponent's side is an *estimate* whenever one is set (the human negotiator's
    ``opponent_ufun``, see :meth:`NegotiationSession.set_opponent_estimate`); those who get this
    tool as configured (admins, or everyone when an admin opened it) can switch to the real one.
    A participant without the tool gets it, limited to the estimate (``estimate_only``), while an
    estimate is set."""

    name = "Negotiation Plot"
    groups = ("visualization",)
    description = "All outcomes in utility space with the Pareto frontier, Nash point and both sides' offers."
    help = """
    **What it shows.** Every possible deal as a grey dot, placed by its value for you (x)
    and for the opponent (y); the **Pareto frontier** (green: deals where neither side can
    gain without the other losing); the **Nash** and **Kalai** points (two standard fair
    compromises); both sides' offers so far; the agreement (red ring); and both sides'
    values on disagreement (dotted lines).

    **Estimate or real.** The banner above the chart says whose numbers the opponent's side
    uses. When an **estimate** of the opponent's preferences is set (for example by your
    Assistant), the chart uses it, and it can be wrong. Otherwise the tool shows the
    opponent's **real** preferences, which only administrators see unless an administrator
    opened the tool to participants; they can switch between the two.

    **How to use it.** Tick the boxes to show or hide layers and hover a dot to see the deal.
    """
    icon = "chart-scatter"
    pane = "lower"
    timing = "load"
    admin_only = True
    order = 9
    max_points = 4000
    #: True for the copy a participant gets only while an estimate is set: never the real ufun
    estimate_only = False

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.values.update(show_outcomes=True, show_pareto=True, show_points=True, opponent="estimate")
        self._cache_key = None
        self._cache: dict = {}

    def opponent(self) -> tuple[Any, str | None]:
        """The opponent's utility function this plot draws and which one it is: ``"estimate"``,
        ``"real"`` or ``None`` (nothing to show)."""
        est = opponent_estimate(self)
        if est is not None and (self.estimate_only or self.values.get("opponent", "estimate") != "real"):
            return est, "estimate"
        if self.estimate_only:
            return None, None
        return self.agent_ufun, "real"

    def _space(self):
        s = self.scenario
        if s is None:
            return None
        opp, kind = self.opponent()
        if opp is None:
            return None
        version = getattr(self.session, "opponent_estimate_version", 0)
        key = (id(s), id(opp), kind, version)
        if self._cache_key != key:
            from negmas.preferences.ops import kalai_points, nash_points, pareto_frontier

            outcomes = list(s.outcome_space.enumerate_or_sample(max_cardinality=self.max_points))
            if kind == "estimate":
                opp = _Normalized(opp, outcomes)
            ufuns = (self.human_ufun, opp)
            pts = [(float(ufuns[0](o)), float(ufuns[1](o))) for o in outcomes]
            try:
                frontier, idx = pareto_frontier(ufuns, outcomes=outcomes, sort_by_welfare=True)
                frontier = sorted((float(a), float(b)) for a, b in frontier)
            except Exception:  # pragma: no cover - continuous / odd spaces
                frontier = []
            try:
                nash = [(float(p[0][0]), float(p[0][1])) for p in nash_points(ufuns, frontier=frontier, outcome_space=s.outcome_space)]
                kalai = [(float(p[0][0]), float(p[0][1])) for p in kalai_points(ufuns, frontier=frontier, outcome_space=s.outcome_space)]
            except Exception:  # pragma: no cover
                nash, kalai = [], []
            self._cache = dict(points=pts, outcomes=outcomes, frontier=frontier, nash=nash, kalai=kalai, opp=opp,
                               kind=kind)
            self._cache_key = key
        return self._cache

    def view(self):
        if self.scenario is None:
            return [ui.text_block("Load a scenario first.", muted=True)]
        sp = self._space()
        if sp is None:
            return [ui.alert("There is no estimate of the opponent's preferences any more.", "neutral")]
        hu, au, kind = self.human_ufun, sp["opp"], sp["kind"]
        opp_label = "Opponent utility (estimate)" if kind == "estimate" else "Opponent utility (real)"
        short = "opponent (est.)" if kind == "estimate" else "opponent"
        human_id = self.session_state.get("human_id")
        fig = go.Figure()
        if self.values.get("show_outcomes", True):
            labels = [self.session.outcome_str(o) for o in sp["outcomes"]]
            fig.add_trace(go.Scattergl(x=[p[0] for p in sp["points"]], y=[p[1] for p in sp["points"]], mode="markers",
                                       name="Outcomes", marker=dict(size=5, color="rgba(100,116,139,0.35)"),
                                       text=labels, hovertemplate=f"%{{text}}<br>you %{{x:.0%}} · {short} %{{y:.0%}}<extra></extra>"))
        if self.values.get("show_pareto", True) and sp["frontier"]:
            fig.add_trace(go.Scatter(x=[p[0] for p in sp["frontier"]], y=[p[1] for p in sp["frontier"]], mode="lines+markers",
                                     name="Pareto frontier" + (" (estimate)" if kind == "estimate" else ""),
                                     line=dict(color="#10b981", width=2, dash="dash" if kind == "estimate" else "solid"),
                                     marker=dict(size=6)))
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
                    hovertemplate=f"%{{text}}<br>you %{{x:.0%}} · {short} %{{y:.0%}}<extra></extra>"))
        m = self.mechanism
        agreement = getattr(getattr(m, "state", None), "agreement", None) if m is not None else None
        if agreement is not None:
            fig.add_trace(go.Scatter(x=[float(hu(agreement))], y=[float(au(agreement))], mode="markers", name="Agreement",
                                     marker=dict(size=18, symbol="circle-open", color="#ef4444", line=dict(width=3))))
        for v, axis in ((float(hu.reserved_value or 0), "x"), (float(au.reserved_value or 0), "y")):
            (fig.add_vline if axis == "x" else fig.add_hline)(v, line_dash="dot", line_color="#ef4444", opacity=0.6)
        fig.update_layout(**base_layout(380, xaxis=dict(title="Your utility", range=[0, 1.02], tickformat=".0%"),
                                        yaxis=dict(title=opp_label, range=[0, 1.02], tickformat=".0%")))
        by = getattr(self.session, "opponent_estimate_by", None)
        who = {"assistant": " by your Assistant", "agent": " by your Assistant"}.get(str(by or ""), "")
        if kind == "estimate":
            banner = ui.alert(f"The opponent's side shows an **estimate** of its preferences (set{who}), "
                              "not its real preferences. It may be wrong.", "warning", title="Estimate")
        else:
            banner = ui.alert("The opponent's side shows the opponent's **real** preferences.", "info",
                              title="Real preferences")
        out = [banner]
        if not self.estimate_only and opponent_estimate(self) is not None:
            out.append(ui.select("opponent", {"The estimate": "estimate", "The real preferences": "real"},
                                 kind, label="Opponent's side"))
        out += [
            ui.row(ui.checkbox("show_outcomes", self.values.get("show_outcomes", True), label="All outcomes"),
                   ui.checkbox("show_pareto", self.values.get("show_pareto", True), label="Pareto frontier"),
                   ui.checkbox("show_points", self.values.get("show_points", True), label="Nash / Kalai")),
            ui.plot(fig),
            ui.text_block("Dotted lines: each side's value on disagreement"
                          + (" (the opponent's as estimated)." if kind == "estimate" else "."), muted=True),
        ]
        return out


class OutcomePlotTool(Tool):
    name = "Outcome Plot"
    groups = ("visualization",)
    description = "Offers placed in the outcome space (any two issues or time)."
    help = """
    **What it shows.** Every offer as a point placed by two issues of your choice (or by
    time), with your offers and your opponent's in different colours.

    **How to use it.** Pick the issues for the X and Y axes; untick *Show your offers* to see
    only your opponent's. It shows *what* was offered, not what it is worth. It is off by
    default: switch it on to use it.
    """
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
                                     name="You" if str(neg) == str(human_id) else "Opponent",
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
    needs_totals = True
    name = "Trace"
    groups = ("information",)
    description = "A table of every offer with its utility."
    help = """
    **What it shows.** One row per offer: the round, the share of the time used, who made
    it, the offer, the message sent with it and what it is worth to you.

    **How to use it.** Click a column header to sort. It is off by default: switch it on to
    use it.
    """
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
            row = {"Step": step, "Time": rel, "By": "You" if str(neg) == str(human_id) else "Opponent",
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
    groups = ("visualization",)
    description = "How often each value of each issue has been offered."
    help = """
    **What it shows.** For each chosen issue, a bar chart counting how often each option has
    been offered, by you and by your opponent.

    **How to use it.** Pick issues with the chips; untick *Your offers* to count only your
    opponent's. Options your opponent offers again and again probably matter to it; options it
    never offers are probably bad for it.
    """
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
                                         name="You" if str(neg) == str(human_id) else "Opponent",
                                         marker_color=party_color(neg, human_id), opacity=0.85))
                fig.update_layout(xaxis=dict(type="category"), barmode="group")
            else:
                for neg in (df["negotiator"].unique() if len(df) else []):
                    fig.add_trace(go.Histogram(x=df[df["negotiator"] == neg][issue.name], nbinsx=20,
                                               name="You" if str(neg) == str(human_id) else "Opponent",
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
    full = df
    if leaderboard:  # every participant: the summary is of human participants only
        from hani2.results import is_simulated

        df = df[~is_simulated(df)]
    from hani2.results import is_practice

    df = df[~is_practice(df)]  # practice rounds stay in the table but never count
    score, per = scenario_scores(df)
    comps: list[ui.Component] = [
        ui.stats(
            ui.stat("Score", f"{score:.1f}", hint="Per scenario: your best results without the worst (counts from 2 negotiations)"),
            ui.stat("Negotiations", len(df)),
            ui.stat("Agreements", int((df.get("status") == "success").sum()) if "status" in df else "—"),
        )
    ]
    if per:
        comps.append(ui.table([{"Scenario": s, "Score": 100 * v, "Negotiations": n} for s, (v, n) in per.items()],
                              formats={"Score": "float"}, sortable=True))
    if leaderboard:
        from hani2.results import leaderboard_by_type, simulated_leaderboard

        lb = make_lb(df)
        if lb:
            comps.append(ui.card(ui.table([{"User": r["user"], "Type": r["participant_type"] or "—", "Score": r["score"],
                                            "Negotiations": r["negotiations"]} for r in lb],
                                          formats={"Score": "float"}), title="Leaderboard (human participants)"))
        strata = leaderboard_by_type(df)
        if len([k for k in strata if k]) > 1 or (len(strata) > 1 and "" in strata):
            for kind, rows in strata.items():
                comps.append(ui.card(ui.table([{"User": r["user"], "Score": r["score"], "Negotiations": r["negotiations"]}
                                               for r in rows], formats={"Score": "float"}),
                                     title=f"Leaderboard: {kind or 'type unknown'}"))
        sim = simulated_leaderboard(df)
        if sim:
            keys = [k for k in sim[0] if k.startswith("pass^")]
            comps.append(ui.card(
                ui.text_block("Simulated participants (not ranked with humans): pass^k of reaching a deal worth at "
                              "least the persona's reservation value.", muted=True),
                ui.table([{"Assistant": r["assistant"], "Persona": r["persona"], "Type": r["participant_type"],
                           "Trials": r["trials"], "Goal rate": r["goal_rate"], **{k: r.get(k) for k in keys}}
                          for r in sim], formats={"Goal rate": "percent", **{k: "percent" for k in keys}}),
                title="Qualifying round (simulated)"))
    df = full
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
    groups = ("information",)
    description = "Your score and every negotiation you completed."
    help = """
    **What it shows.** Your score (the average of your best result in each scenario), how
    many negotiations you finished and how many ended in agreement, a score per scenario and
    a table of every negotiation.

    **How to use it.** Choose the table's columns with *Columns*. It updates when a
    negotiation ends. This tool is always on.
    """
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
    groups = ("information",)
    description = "Every participant's results and a leaderboard (admins only)."
    help = """
    **What it shows.** Every negotiation of every participant, the overall scores and a
    leaderboard ranked by score.

    **How to use it.** Search the table, choose its columns and sort by any column. Only
    administrators get this tool.
    """
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
OPP_COLUMN = "Opponent (estimate)"


class UtilitySelectorTool(OutcomeSelector):
    needs_totals = True
    name = "Utility-based Selector"
    groups = ("recommendation",)
    description = "Browse every outcome whose utility for you is in a chosen range and use one as your offer."
    help = """
    **What it shows.** A table of the deals whose value *for you* lies in a range you
    choose, best first.

    **How to use it.** Set *Minimum utility* and *Range width* with the sliders (70% and 10%
    lists every deal worth 70–80% to you). Click a row to copy that deal into your
    counter-offer, then press **Send offer** to send it as your offer right away (with the
    message you typed, if any), or adjust it in your counter-offer and send it from there.

    **With an estimate of the opponent.** When an estimate of the opponent's preferences is
    set (for example by your Assistant), the table can also show what each deal is worth to the
    opponent *by that estimate*, and *Choose deals by* can switch the sliders to the opponent's
    estimated utility, so you can look for deals the opponent likely accepts while still seeing
    their value for you. Estimates can be wrong.
    """
    icon = "list-filter"
    pane = "side"
    timing = "start"
    order = 0
    sends_offer = True
    agent_hint = ("Select a row with action 'pick' to fill the participant's counter-offer with that deal; "
                  "'send_offer' then sends the picked deal as their offer.")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._inverter = None
        self._minmax = None
        self._cache_ufun = None  # the ufun the two caches above were built for
        self._opp_inverter = None
        self._opp_minmax = None
        self._opp_key = None  # (id of the estimate, the session's estimate version) the two above are for
        # width 100% by default: the range runs from the minimum slider up to the best outcome.
        self.values.update(min_util=70, width=100, show_opponent=True, rank_by="me")

    def negotiation_started(self, session_state, nmi):
        self._inverter = None
        self._minmax = None
        super().negotiation_started(session_state, nmi)

    def _check_cache(self) -> None:
        """Drop the caches when the ufun changed (the next scenario loads before it starts)."""
        if self._cache_ufun is not self.human_ufun:
            self._inverter = None
            self._minmax = None
            self._cache_ufun = self.human_ufun

    # -- the opponent estimate (only while one is set) ---------------------------------
    def _estimate(self):
        est = opponent_estimate(self)
        key = (id(est), getattr(self.session, "opponent_estimate_version", 0)) if est is not None else None
        if key != self._opp_key:
            self._opp_inverter = None
            self._opp_minmax = None
            self._opp_key = key
        return est

    def _by_opponent(self) -> bool:
        return self.values.get("rank_by") == "opponent" and self._estimate() is not None

    def _ranking_ufun(self):
        return self._estimate() if self._by_opponent() else self.human_ufun

    def _opp_normalized(self, u: float) -> float:
        est = self._estimate()
        if self._opp_minmax is None:
            try:
                mn, mx = est.minmax()
                self._opp_minmax = (float(mn), float(mx))
            except Exception:
                self._opp_minmax = (0.0, 1.0)
        mn, mx = self._opp_minmax
        return (u - mn) / (mx - mn) if mx - mn > 1e-12 else 1.0

    def _get_inverter(self):
        if self._by_opponent():
            if self._opp_inverter is None:
                self._opp_inverter = self._estimate().invert()
            return self._opp_inverter
        self._check_cache()
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
        """The chosen range on the normalized [0, 1] scale (0 = worst outcome, 1 = best)."""
        lo = float(self.values.get("min_util", 70)) / 100
        return lo, min(1.0, lo + float(self.values.get("width", 100)) / 100)

    def _normalized(self, u: float) -> float:
        """A raw utility on the sliders' scale, so un-normalized ufuns show 0-100% too."""
        self._check_cache()
        if self._minmax is None:
            try:
                mn, mx = self.human_ufun.minmax()
                self._minmax = (float(mn), float(mx))
            except Exception:
                self._minmax = (0.0, 1.0)
        mn, mx = self._minmax
        return (u - mn) / (mx - mn) if mx - mn > 1e-12 else 1.0

    def _outcomes(self) -> list:
        if self._ranking_ufun() is None:
            return []
        try:
            return list(self._get_inverter().some(self._range(), normalized=True))
        except Exception:
            return []

    def selector_view(self):
        est = self._estimate()
        by_opp = self._by_opponent()
        show_opp = est is not None and (by_opp or bool(self.values.get("show_opponent", True)))
        rows = []
        for o in self._outcomes()[:500]:
            d = self.outcome_dict(o) or {}
            d["Utility"] = self._normalized(float(self.human_ufun(o)))
            if show_opp:
                d[OPP_COLUMN] = self._opp_normalized(float(est(o)))
            rows.append(d)
        key = OPP_COLUMN if by_opp else "Utility"
        rows.sort(key=lambda r: -r[key])
        sel = self.values.get("selected")
        out = []
        if est is not None:
            out += [
                ui.alert("An **estimate** of the opponent's preferences is set: the opponent's numbers here come "
                         "from it, not from the opponent's real preferences.", "warning"),
                ui.row(
                    ui.select("rank_by", {"My utility": "me", "The opponent's estimated utility": "opponent"},
                              "opponent" if by_opp else "me", label="Choose deals by"),
                    *([] if by_opp else [ui.checkbox("show_opponent", show_opp, label="Show the opponent's estimate")]),
                    align="end"),
            ]
        out += [
            ui.slider("min_util", 0, 100, self.values.get("min_util", 70),
                      label="Minimum utility for the opponent (estimate)" if by_opp else "Minimum utility", suffix="%"),
            ui.slider("width", 1, 100, self.values.get("width", 100), label="Range width", suffix="%"),
            ui.table(rows, on_select="pick", formats={"Utility": "percent"} | ({OPP_COLUMN: "percent"} if show_opp else {}),
                     page_size=15,
                     selected=sel, max_height=320)
            if rows
            else ui.alert("No outcome in this utility range.", "neutral"),
        ]
        return out

    def on_input(self, name, value):
        self.unpick()
        super().on_input(name, value)

    def on_action(self, action, payload):
        if action == "pick":
            row = payload.get("row") or {}
            return self.pick({k: v for k, v in row.items() if k not in ("Utility", OPP_COLUMN)}, payload.get("index"))
        return super().on_action(action, payload)

    def get_outcome(self) -> Outcome | None:
        try:
            return self._get_inverter().one_in(self._range(), normalized=True)
        except Exception:
            return None


BAR_MODES = {
    "any": "Any offer",
    "some": "Up to 10 offers",
    "all": "All offers",
    "opp_best": "Best for the opponent",
    "opp_top": "Top 10 for the opponent",
}
OPP_MODES = ("opp_best", "opp_top")


class UtilityBarTool(OutcomeSelector):
    """The graphical utility inverter: click or drag on a 0-100% bar of *your* utility and get
    offers from that part of it (one, up to ten, all, or the best for the opponent)."""

    needs_totals = True
    name = "Utility Bar"
    groups = ("recommendation",)
    description = "Click or drag on a bar of what deals are worth to you and get offers from that part."
    help = """
    **What it shows.** A bar of what deals are worth *to you*, from 0% (your worst deal) to
    100% (your best). The grey columns show how many deals there are at each value; the
    marks show your value on disagreement, the opponent's offer on the table and your current
    offer.

    **How to use it.** **Drag** across the bar to choose a part of it (for example 60-80%),
    or **click** a point to get the deals *nearest* to that value. Then choose what you want:

    * **Any offer**: one deal from that part (press **Another** for a different one);
    * **Up to 10 offers**: up to ten deals spread across that part;
    * **All offers**: every deal in that part, best for you first;
    * **Best for the opponent** / **Top 10 for the opponent**: the deals in that part worth most
      to the opponent (only when an estimate of the opponent's preferences is set, or for
      administrators, who see the real ones).

    Click a row to copy that deal into your counter-offer, then press **Send offer** to send
    it as your offer right away (with the message you typed, if any), or adjust it in your
    counter-offer and send it from there. The keyboard works too: the arrow keys move the
    selection, shift and an arrow widens it.

    **The opponent's numbers** come from an *estimate* when one is set, and estimates can be
    wrong; a banner says which you see.
    """
    agent_hint = ("Set the input 'area' to [low, high] in percent of the participant's utility (or [x, x] for the "
                  "deals nearest x) and 'mode' to one of any, some, all, opp_best, opp_top; then select a row "
                  "with action 'pick' to fill the participant's counter-offer with it; 'send_offer' then sends "
                  "the picked deal as their offer.")
    icon = "ruler-dimension-line"
    pane = "side"
    timing = "start"
    order = -10
    sends_offer = True
    #: outcomes considered at most (larger outcome spaces are sampled)
    max_outcomes = 200_000
    #: rows shown at most by "All offers"
    max_rows = 1000
    #: how many deals "Up to 10" and "Top 10" give, and how many nearest deals a click considers
    k = 10
    #: a selection narrower than this (in percent) is a click
    click_width = 0.5
    bins = 40

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.values.update(area=[70, 100], mode="any", opponent="estimate", draw=0, selected=None)
        self._mine_key = None
        self._mine = None  # (outcomes, normalized utilities as a numpy array)
        self._opp_key = None
        self._opp = None

    # -- utilities --------------------------------------------------------------------
    def _space(self):
        """Every outcome (sampled above :attr:`max_outcomes`) and their normalized utility for the human."""
        import numpy as np

        uf, s = self.human_ufun, self.scenario
        key = (id(uf), id(s))
        if self._mine_key != key:
            self._mine_key, self._mine, self._opp_key, self._opp = key, None, None, None
        if self._mine is None:
            if uf is None or s is None:
                return [], np.zeros(0)
            outs = list(s.outcome_space.enumerate_or_sample(max_cardinality=self.max_outcomes))
            self._mine = (outs, self._normalize([float(uf(o)) for o in outs], uf))
        return self._mine

    @staticmethod
    def _normalize(vals: list[float], ufun=None):
        """Utilities on a 0..1 scale (0 = the worst deal, 1 = the best), from the ufun's own
        ``minmax`` when it has one, so the numbers match the other tools."""
        import numpy as np

        a = np.asarray(vals, dtype=float)
        a = np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)
        mn = mx = None
        try:
            if ufun is not None:
                mn, mx = (float(x) for x in ufun.minmax())
        except Exception:
            mn = mx = None
        if mn is None or mx is None or not (np.isfinite(mn) and np.isfinite(mx)):
            mn, mx = (float(a.min()), float(a.max())) if len(a) else (0.0, 1.0)
        return np.clip((a - mn) / (mx - mn), 0.0, 1.0) if mx - mn > 1e-12 else np.ones_like(a)

    def opponent(self) -> tuple[Any, str | None]:
        """The opponent's utility function the opponent modes use and which one it is:
        ``"estimate"`` (an estimate is set), ``"real"`` (only for those who may see it:
        administrators, or everyone when ``tools.show_opponent_utility`` is on) or ``None``."""
        est = opponent_estimate(self)
        real = self.agent_ufun if self.may_see_opponent else None
        if est is not None and (real is None or self.values.get("opponent", "estimate") != "real"):
            return est, "estimate"
        if real is not None:
            return real, "real"
        return None, None

    def _opp_utils(self):
        import numpy as np

        ufun, kind = self.opponent()
        if ufun is None:
            return None, None
        outs, _ = self._space()
        key = (id(ufun), kind, getattr(self.session, "opponent_estimate_version", 0), self._mine_key)
        if self._opp_key != key:
            try:
                self._opp = self._normalize([float(ufun(o)) for o in outs], ufun if kind == "real" else None)
            except Exception:
                self._opp = np.zeros(len(outs))
            self._opp_key = key
        return self._opp, kind

    # -- the selection ------------------------------------------------------------------
    def area(self) -> tuple[float, float]:
        """The chosen part of the bar in percent, ``(lo, hi)``; ``lo == hi`` for a click."""
        v = ui.range_value(self.values.get("area") or [70, 100])
        try:
            lo, hi = sorted(max(0.0, min(100.0, float(x))) for x in list(v)[:2])
        except Exception:
            lo, hi = 70.0, 100.0
        return lo, hi

    def is_click(self) -> bool:
        lo, hi = self.area()
        return hi - lo < self.click_width

    def mode(self) -> str:
        m = self.values.get("mode", "any")
        if m not in BAR_MODES or (m in OPP_MODES and self.opponent()[0] is None):
            return "any"
        return m

    def _candidates(self):
        """Indices of the deals the selection covers: those in the dragged range, or for a click
        the nearest ones (the nearest deal and its ties; the :attr:`k` nearest for the modes that
        give several or rank by the opponent)."""
        import numpy as np

        _, mine = self._space()
        if not len(mine):
            return np.zeros(0, dtype=int)
        lo, hi = (x / 100 for x in self.area())
        if not self.is_click():
            return np.flatnonzero((mine >= lo - 1e-9) & (mine <= hi + 1e-9))
        dist = np.abs(mine - (lo + hi) / 2)
        if self.mode() in ("any", "all"):
            return np.flatnonzero(dist <= dist.min() + 1e-9)
        return np.argsort(dist, kind="stable")[: self.k]

    def results(self) -> list[int]:
        """The deals the current selection and mode give, as indices into the outcome list, in
        the order they are listed."""
        import numpy as np

        cand = self._candidates()
        if not len(cand):
            return []
        _, mine = self._space()
        m = self.mode()
        by_me = cand[np.argsort(-mine[cand], kind="stable")]
        if m == "any":
            rng = random.Random(hash((tuple(self.area()), int(self.values.get("draw", 0) or 0), len(cand))))
            return [int(rng.choice(list(cand)))]
        if m == "all":
            return [int(i) for i in by_me]
        if m == "some":
            if len(by_me) <= self.k:
                return [int(i) for i in by_me]
            # spread across the part: from its best to its worst deal
            picks = np.linspace(0, len(by_me) - 1, self.k).round().astype(int)
            return [int(by_me[j]) for j in dict.fromkeys(picks.tolist())]
        opp, _ = self._opp_utils()
        if opp is None:
            return [int(i) for i in by_me[:1]]
        # best for the opponent first; between equals, better for the human first
        order = sorted(cand.tolist(), key=lambda i: (-float(opp[i]), -float(mine[i])))
        return [int(i) for i in order[: 1 if m == "opp_best" else self.k]]

    # -- the view ----------------------------------------------------------------------
    def _bar(self, opp):
        import numpy as np

        _, mine = self._space()
        counts = np.histogram(mine, bins=self.bins, range=(0.0, 1.0))[0] if len(mine) else np.zeros(self.bins)
        overlay = None
        if opp is not None and len(mine):
            idx = np.minimum((mine * self.bins).astype(int), self.bins - 1)
            best = np.full(self.bins, np.nan)
            np.fmax.at(best, idx, opp)
            overlay = [None if np.isnan(x) else round(float(x), 4) for x in best]
        marks = []
        uf = self.human_ufun

        def pct_of(u):
            return float(self._normalize([float(u)], uf)[0]) * 100

        rv = getattr(uf, "reserved_value", None)
        if rv is not None and np.isfinite(float(rv)):
            marks.append({"value": round(pct_of(rv), 2), "label": "No deal", "kind": "bad"})
        sess = getattr(self, "session", None)
        for fn, label, kind in (("partner_offer", "Their offer", "opponent"), ("draft_outcome", "Your offer", "you")):
            try:
                o = getattr(sess, fn)() if sess is not None else None
                if o is not None and None not in o:
                    marks.append({"value": round(pct_of(uf(o)), 2), "label": label, "kind": kind})
            except Exception:
                pass
        return [int(c) for c in counts], overlay, marks

    def _row(self, i: int, mine, opp, opp_col: str | None) -> dict[str, Any]:
        outs, _ = self._space()
        d = self.outcome_dict(outs[i]) or {}
        d["Utility"] = float(mine[i])
        if opp_col:
            d[opp_col] = float(opp[i])
        return d

    def selector_view(self):
        outs, mine = self._space()
        if not outs:
            return [ui.alert("No outcomes to choose from yet.", "neutral")]
        ufun_opp, kind = self.opponent()
        opp, _ = self._opp_utils()
        m = self.mode()
        lo, hi = self.area()
        click = self.is_click()
        counts, overlay, marks = self._bar(opp)
        out: list[ui.Component] = []
        modes = {v: k for k, v in BAR_MODES.items() if k not in OPP_MODES or ufun_opp is not None}
        if kind == "estimate":
            out.append(ui.alert("The opponent's numbers come from an **estimate** of their preferences, which can be "
                                "wrong.", "warning"))
        elif kind == "real":
            out.append(ui.alert("The opponent's numbers are their **real** preferences.", "info"))
        bar_hint = "Click a point for the nearest deals, or drag across a part of the bar."
        out.append(ui.range_bar("area", [lo, hi], label="What the deal is worth to you", density=counts,
                                overlay=overlay, overlay_label=("Best for the opponent here" if overlay else None),
                                marks=marks, hint=bar_hint))
        controls = [ui.select("mode", modes, m, label="Give me")]
        if kind is not None and self.may_see_opponent and opponent_estimate(self) is not None:
            controls.append(ui.select("opponent", {"The estimate": "estimate", "Their real preferences": "real"},
                                      self.values.get("opponent", "estimate"), label="Opponent's numbers"))
        out.append(ui.row(*controls, align="end"))
        res = self.results()
        where = f"nearest to {lo:.0f}%" if click else f"between {lo:.0f}% and {hi:.0f}%"
        if not res:
            out.append(ui.alert(f"No deal is worth {where} to you. Drag across a wider part of the bar.", "neutral"))
            return out
        opp_col = None
        if opp is not None:
            opp_col = "Opponent (estimate)" if kind == "estimate" else "Opponent"
        shown = res[: self.max_rows]
        rows = [self._row(i, mine, opp, opp_col) for i in shown]
        n_cand = len(self._candidates())
        summary = {
            "any": f"One deal {where}" + (f" (of {n_cand})" if n_cand > 1 else "") + ".",
            "some": f"{len(res)} deal{'s' if len(res) != 1 else ''} {where}, spread from the best to the worst for you.",
            "all": f"All {len(res)} deal{'s' if len(res) != 1 else ''} {where}, best for you first.",
            "opp_best": f"The deal {where} worth most to the opponent.",
            "opp_top": f"The {len(res)} deal{'s' if len(res) != 1 else ''} {where} worth most to the opponent.",
        }[m]
        if len(res) > len(shown):
            summary += f" The first {len(shown)} are listed."
        out.append(ui.text_block(summary, muted=True))
        sel = self.values.get("selected")
        formats = {"Utility": "percent"} | ({opp_col: "percent"} if opp_col else {})
        out.append(ui.table(rows, on_select="pick", formats=formats, page_size=10, selected=sel, max_height=300,
                            sortable=len(rows) > 1))
        if m == "any" and n_cand > 1:
            out.append(ui.button("Another", "draw", icon="dices", variant="ghost"))
        return out

    def draft_changed(self, session_state, draft) -> None:
        super().draft_changed(session_state, draft)
        self.refresh()

    def on_input(self, name, value):
        self.unpick()
        if name == "area":
            # a new part of the bar: a new random pick for "Any offer"
            self.values["draw"] = 0
        super().on_input(name, value)

    def on_action(self, action, payload):
        if action == "pick":
            row = payload.get("row") or {}
            return self.pick({k: v for k, v in row.items() if k not in ("Utility", "Opponent", "Opponent (estimate)")},
                             payload.get("index"))
        if action == "draw":
            self.values["draw"] = int(self.values.get("draw", 0) or 0) + 1
            self.unpick()
            self.refresh()
            return None
        return super().on_action(action, payload)

    def get_outcome(self) -> Outcome | None:
        res = self.results()
        if not res:
            return None
        sel = self.values.get("selected")
        i = res[sel] if isinstance(sel, int) and 0 <= sel < len(res) else res[0]
        return self._space()[0][i]


class RandomOutcomeTool(OutcomeSelector):
    name = "Random"
    groups = ("recommendation",)
    description = "Fill the offer with a random outcome and send it (admins only)."
    help = """
    **What it does.** **Generate** puts a random deal into your counter-offer (press it again
    for another); **Send offer** then sends that deal as your offer, with the message you typed,
    if any. Only administrators get this tool; it is meant for testing.
    """
    icon = "dices"
    admin_only = True
    order = 20
    sends_offer = True
    nothing_picked = "Generate a deal first."
    agent_hint = "Press 'generate' to fill the participant's counter-offer with a random deal; 'send_offer' sends it."

    def selector_view(self):
        comps: list[ui.Component] = [ui.markdown("Samples a random outcome and puts it in your offer.")]
        picked = self.picked_outcome()
        if picked:
            comps.append(ui.outcome(picked, label="Generated deal"))
        comps.append(ui.button("Generate another" if picked else "Generate", "generate", icon="dices",
                               variant="secondary", disabled=not self.can_set(), full=True))
        return comps

    def on_action(self, action, payload):
        if action == "generate":
            r = self.pick(self.outcome_dict(self.get_outcome()) or {})
            if not r.get("ok", True):
                self.toast(r.get("error", "Could not set the offer"), "warning")
            return r
        return super().on_action(action, payload)

    def get_outcome(self):
        s = self.scenario
        if s is None:
            return None
        try:
            return s.outcome_space.random_outcome()
        except Exception:
            return random.choice(list(s.outcome_space.enumerate_or_sample(max_cardinality=1000)))


class ResponseGeneratorTool(OutcomeSelector):
    needs_totals = True
    name = "LLM"
    groups = ("recommendation",)
    description = "Describe what you want in plain words and let an LLM write the offer and message."
    help = """
    **What it does.** Turns an instruction in plain words ("propose a fair middle ground",
    "improve my last offer slightly") into a suggested offer and/or message.

    **How it works.** Choose whether it writes the message, the offer or both, and press
    **Generate**. With no instruction the button reads **Recommend an offer** (or **Write a
    message**) and asks for exactly that. When you have an Assistant, your Assistant answers,
    with what it knows of the negotiation and your conversation; otherwise your instruction, the
    issues, your preferences and the recent offers go to the configured language model. Check
    the suggestion. **Set offer** copies it into your
    counter-offer (to change it or send it from there); **Send offer** sends it as your offer
    right away, with its message. Only administrators get this tool.
    """
    icon = "sparkles"
    admin_only = True
    order = 10
    sends_offer = True
    nothing_picked = "Generate a suggestion first."
    agent_hint = ("Write the input 'instruction' and press 'generate'; then 'apply' copies the suggestion into the "
                  "participant's counter-offer and message, and 'send_offer' sends it as their offer.")

    #: what an empty instruction asks for, and the Generate button's text then, per mode
    DEFAULT_INSTRUCTIONS = {
        "both": ("Recommend an offer, with a message to go with it.", "Recommend an offer"),
        "outcome_only": ("Recommend an offer.", "Recommend an offer"),
        "text_only": ("Write a message to the opponent for my current offer.", "Write a message"),
    }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.values.update(instruction="", mode="both")
        self.generated: dict[str, Any] | None = None
        self.status = ""
        self.busy = False
        self._by_agent = False

    def assistant(self):
        """The participant's Assistant when it writes the suggestions (it is on and has the
        ``llm_tool`` capability for the chosen mode), else ``None``."""
        sa = getattr(self.session, "support_agent", None)
        if sa is None or not getattr(sa, "user_enabled", False):
            return None
        answers = getattr(sa, "answers_llm_tool", None)
        return sa if answers is None or answers(self.values.get("mode", "both")) else None

    def instruction(self) -> str:
        """The typed instruction, or the mode's default when nothing is typed."""
        typed = str(self.values.get("instruction") or "").strip()
        return typed or self.DEFAULT_INSTRUCTIONS.get(self.values.get("mode", "both"), self.DEFAULT_INSTRUCTIONS["both"])[0]

    def negotiation_started(self, session_state, nmi):
        self.generated = None
        self.status = ""
        super().negotiation_started(session_state, nmi)

    def view(self):
        from hani2.llm_service import get_llm_status

        comps: list[ui.Component] = []
        if self.assistant() is not None:
            comps.append(ui.text_block("Your Assistant writes the suggestions.", muted=True))
        else:
            st = get_llm_status()
            if not st.get("configured"):
                comps.append(ui.alert(f"The LLM is not configured (provider `{st.get('provider')}`).", "warning"))
        empty_label = self.DEFAULT_INSTRUCTIONS.get(self.values.get("mode", "both"), self.DEFAULT_INSTRUCTIONS["both"])[1]
        comps += [
            ui.textarea("instruction", self.values.get("instruction", ""), rows=3,
                        placeholder="e.g. Propose a fair middle ground, or: improve my last offer slightly "
                                    "(leave it empty for a recommendation)"),
            ui.radio("mode", {"Text & offer": "both", "Text only": "text_only", "Offer only": "outcome_only"},
                     self.values.get("mode", "both")),
            ui.button("Generating…" if self.busy else "Generate", "generate", variant="primary", icon="sparkles",
                      disabled=self.busy or not self.can_set(), full=True,
                      empty_label=None if self.busy else empty_label, empty_input="instruction"),
        ]
        if self.status:
            comps.append(ui.alert(self.status, "error" if self.status.startswith("Error") else "info"))
        g = self.generated
        if g:
            if g.get("outcome"):
                comps.append(ui.outcome(g["outcome"], g.get("utility"), label="Suggested offer"))
            if g.get("text"):
                comps.append(ui.card(ui.markdown(g["text"]), title="Suggested message"))
            reason = self.send_blocker()
            comps.append(ui.row(
                ui.button("Set offer", "apply", variant="secondary", icon="arrow-left-to-line",
                          tooltip="Copy the suggestion into your counter-offer and message"),
                ui.button(self.send_label, "send_offer", variant="primary", icon="send", disabled=reason is not None,
                          tooltip=reason or "Send the suggestion as your offer, with its message"),
            ))
        return comps

    # the suggestion is what Send offer sends (an edited counter-offer does not discard it)
    def picked_outcome(self):
        g = self.generated
        if not g:
            return None
        if g.get("outcome"):
            return dict(g["outcome"])
        # a message only: it goes with the counter-offer as it is
        return dict(self.session.draft) if g.get("text") and self.session.draft else None

    def unpick(self) -> None:
        self.generated = None

    def draft_changed(self, session_state, draft) -> None:
        if self.generated and not self.generated.get("outcome"):
            self.refresh()  # a message-only suggestion is sent with the current counter-offer

    def send_outcome(self) -> dict:
        reason = self.send_blocker()
        if reason:
            return {"ok": False, "error": reason}
        g = dict(self.generated or {})
        if g.get("outcome"):
            r = self.set_offer(g["outcome"])
            if not r.get("ok", True):
                return r
        if g.get("text") and self.session.admin_prefs.get("allow_text_human", True):
            r = self.set_text(g["text"])
            if not r.get("ok", True):
                return r
        res = self.session_state["actions"]["reject_counter"]() or {}
        if res.get("ok"):
            self.generated = None
            self.session.emit({"type": "draft_text", "text": ""})
            self.refresh()
        return res

    def on_input(self, name, value):
        self.values[name] = value  # no re-render while typing
        if name == "mode":
            self.refresh()  # the button's text follows the mode

    def on_action(self, action, payload):
        if action == "generate":
            if payload.get("instruction") is not None:
                self.values["instruction"] = payload["instruction"]
            if payload.get("mode") in self.DEFAULT_INSTRUCTIONS:
                self.values["mode"] = payload["mode"]
            self._by_agent = self.session._actor() == "agent"
            self.busy, self.status = True, ""
            self.refresh()
            self.session.submit(self._generate)
        elif action == "apply" and self.generated:
            if self.generated.get("outcome"):
                self.set_offer(self.generated["outcome"])
            if self.generated.get("text"):
                self.set_text(self.generated["text"])
            self.toast("Copied into your offer", "success")
        elif action == "send_offer":
            r = self.send_outcome()
            if not r.get("ok", True):
                self.toast(r.get("error", "Could not send the offer"), "warning")
            return r

    def _generate(self):
        from hani2.connections import llm_error
        from hani2.llm_service import generate_from_instruction

        try:
            instr = self.instruction()
            mode = self.values.get("mode", "both")
            # the Assistant answers the participant; when it pressed Generate itself (it is waiting on
            # this tool, holding its turn) or does not answer, the tool's own prompt does
            sa = None if self._by_agent else self.assistant()
            suggestion = sa.suggest_offer(instr, mode) if sa is not None else None
            if suggestion is not None:
                if suggestion.get("error"):
                    self.status = f"Error: {suggestion['error']}"
                    return
                out = suggestion.get("outcome") or None
                utility = None
                if out:
                    try:
                        utility = self.session.utility(tuple(out.get(i.name) for i in self.issues))
                    except Exception:  # noqa: BLE001
                        utility = None
                self.generated = {"outcome": out, "text": suggestion.get("text"), "utility": utility}
                self.status = ""
                return
            res = generate_from_instruction(instruction=instr, issues=self.issues, context=self.session.llm_context(),
                                            output_mode=mode)
            if res.error:
                self.status = f"Error: {llm_error(res.error, admin=self.session.is_admin)}"
                return
            out = self.outcome_dict(res.outcome) if res.outcome is not None else None
            self.generated = {"outcome": out, "text": res.text,
                              "utility": self.session.utility(res.outcome) if res.outcome is not None else None}
            self.status = ""
        except Exception as e:  # noqa: BLE001
            self.status = f"Error: {llm_error(e, admin=self.session.is_admin)}"
        finally:
            self.busy = False
            self.refresh()
