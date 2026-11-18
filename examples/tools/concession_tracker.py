"""Step 3 - a live chart: how fast is the opponent conceding?

``action_requested`` runs on every turn; it computes the opponent's concession
and calls ``refresh()`` (the base class does that too) so the chart redraws.
Any Plotly figure works with ``ui.plot``.
"""

import plotly.graph_objects as go

from hani2.tools import Tool, ui
from hani2.tools.plotting import AGENT_COLOR, base_layout


class ConcessionTracker(Tool):
    name = "Concession Tracker"
    description = "The utility of the opponent's offers for you, and a projection to the deadline."
    help = """
    **What it shows.** What each of your opponent's offers is worth to you over time, and a
    dotted line projecting that trend to the deadline.

    **How it works.** The concession rate is the change in value between the opponent's first
    and latest offers, divided by the time between them. The projection assumes the opponent
    keeps conceding at that rate. It needs at least two opponent offers.
    """
    icon = "trending-up"
    pane = "lower"

    def view(self):
        me = self.session_state.get("human_id")
        points = [(row[1], float(self.human_ufun(row[4]))) for row in self.trace() if row[3] != me and row[4] is not None]
        if len(points) < 2:
            return [ui.text_block("Waiting for at least two opponent offers.", muted=True)]
        (t0, u0), (t1, u1) = points[0], points[-1]
        rate = (u1 - u0) / max(t1 - t0, 1e-6)
        projected = max(0.0, min(1.0, u1 + rate * (1 - t1)))
        fig = go.Figure(go.Scatter(x=[p[0] for p in points], y=[100 * p[1] for p in points], mode="lines+markers",
                                   name="Opponent offers", line=dict(color=AGENT_COLOR, width=3)))
        fig.add_trace(go.Scatter(x=[t1, 1.0], y=[100 * u1, 100 * projected], mode="lines", name="Projection",
                                 line=dict(color=AGENT_COLOR, dash="dot")))
        fig.update_layout(**base_layout(240, xaxis=dict(range=[0, 1], title="time"), yaxis=dict(range=[0, 100], ticksuffix="%")))
        return [
            ui.stats(
                ui.stat("Concession per 10% of time", f"{10 * rate:+.1%}"),
                ui.stat("Projected final offer", f"{projected:.0%}"),
            ),
            ui.plot(fig),
        ]
