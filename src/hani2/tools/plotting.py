"""Shared helpers for plotting tools: trace → DataFrame and a consistent look.

Figures returned by tools are themed by the frontend (fonts, light/dark
colours), so keep layouts minimal and use :data:`HUMAN_COLOR` /
:data:`AGENT_COLOR` for the two parties.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

TRACE_COLUMNS = ("time", "relative_time", "step", "negotiator", "offer", "responses", "state", "text", "data")
HUMAN_COLOR = "#4f46e5"
AGENT_COLOR = "#f59e0b"
NEUTRAL_COLOR = "#64748b"
SEQUENCE = [HUMAN_COLOR, AGENT_COLOR, "#10b981", "#ef4444", "#06b6d4", "#a855f7"]


def base_layout(height: int = 260, legend: bool = True, **kw: Any) -> dict[str, Any]:
    layout = dict(
        height=height,
        margin=dict(l=48, r=12, t=12, b=40),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="closest",
    )
    layout.update(kw)
    return layout


def party_color(name: str, human_id: str) -> str:
    return HUMAN_COLOR if str(name) == str(human_id) else AGENT_COLOR


def trace_frame(trace: list, issues: list | None = None) -> pd.DataFrame:
    """The mechanism's ``full_trace`` as a DataFrame, with one column per issue."""
    rows = [dict(zip(TRACE_COLUMNS, (list(r) + [None] * 9)[:9])) for r in trace]
    df = pd.DataFrame.from_records(rows, columns=list(TRACE_COLUMNS))
    if issues:
        for i, issue in enumerate(issues):
            df[issue.name] = df["offer"].apply(lambda x, idx=i: x[idx] if x else None)
    return df
