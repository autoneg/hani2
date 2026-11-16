"""Declarative UI components for tools.

A tool's :meth:`~hani2.tools.Tool.view` returns a list of components built with
these helpers. They are plain JSON-able dicts that the web frontend renders, so
a tool author only ever writes Python.

Interactive components:

* **Inputs** (``select``, ``multiselect``, ``slider``, ``number``, ``checkbox``,
  ``switch``, ``radio``, ``text``, ``textarea``) carry a ``name``. When the user
  changes one, the tool's :meth:`~hani2.tools.Tool.on_input` is called with
  ``(name, value)``. The default implementation stores the value in
  ``self.values[name]`` and re-renders.
* **Buttons** carry an ``action``. Clicking calls
  :meth:`~hani2.tools.Tool.on_action` with ``(action, payload)`` where
  ``payload`` is the button's ``payload`` plus the current values of all inputs.
* **Tables** may set ``on_select=<action>``; clicking a row calls ``on_action``
  with ``payload={"row": <row dict>, "index": <int>}``.

Example::

    from hani2.tools import Tool, ui

    class Hello(Tool):
        name = "Hello"

        def view(self):
            return [
                ui.markdown("### Hello"),
                ui.slider("level", 0, 100, self.values.get("level", 50), label="Level"),
                ui.button("Shout", action="shout"),
            ]

        def on_action(self, action, payload):
            self.toast(f"Level is {self.values.get('level', 50)}")
"""

from __future__ import annotations

import json
import math
from typing import Any, Iterable, Sequence

Component = dict[str, Any]

__all__ = [
    "Component",
    "markdown",
    "text_block",
    "heading",
    "alert",
    "badge",
    "stat",
    "stats",
    "kv",
    "plot",
    "table",
    "button",
    "select",
    "multiselect",
    "slider",
    "number",
    "checkbox",
    "switch",
    "radio",
    "text",
    "textarea",
    "row",
    "column",
    "grid",
    "card",
    "divider",
    "progress",
    "html",
    "outcome",
    "jsonable",
]


def jsonable(x: Any) -> Any:
    """Convert numpy / negmas values to JSON-friendly Python values."""
    try:
        import numpy as np

        if isinstance(x, np.generic):
            x = x.item()
        elif isinstance(x, np.ndarray):
            return [jsonable(v) for v in x.tolist()]
    except Exception:  # pragma: no cover
        pass
    if isinstance(x, float):
        if math.isnan(x):
            return None
        if math.isinf(x):
            return "inf" if x > 0 else "-inf"
        return x
    if isinstance(x, (str, int, bool)) or x is None:
        return x
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [jsonable(v) for v in x]
    try:
        import numpy as np

        if isinstance(x, np.floating):
            return jsonable(float(x))
    except Exception:  # pragma: no cover
        pass
    if hasattr(x, "isoformat"):
        return x.isoformat()
    return str(x)


def _c(_type: str, **kw: Any) -> Component:
    return {"type": _type, **{k: v for k, v in kw.items() if v is not None}}


# -- static content ---------------------------------------------------------
def markdown(text: str, *, size: str | None = None) -> Component:
    """Markdown (GitHub flavoured; tables supported). ``size``: sm | md | lg."""
    return _c("markdown", text=str(text), size=size)


def text_block(text: str, *, muted: bool = False) -> Component:
    return _c("text", text=str(text), muted=muted)


def heading(text: str, level: int = 3) -> Component:
    return _c("heading", text=str(text), level=level)


def alert(text: str, kind: str = "info", title: str | None = None) -> Component:
    """``kind``: info | success | warning | error | neutral (markdown text)."""
    return _c("alert", text=str(text), kind=kind, title=title)


def badge(text: str, kind: str = "neutral") -> Component:
    return _c("badge", text=str(text), kind=kind)


def stat(label: str, value: Any, *, hint: str | None = None, kind: str | None = None) -> Component:
    return _c("stat", label=label, value=jsonable(value), hint=hint, kind=kind)


def stats(*items: Component) -> Component:
    return _c("stats", children=list(items))


def kv(data: dict[str, Any] | Sequence[tuple[str, Any]], title: str | None = None) -> Component:
    items = list(data.items()) if isinstance(data, dict) else list(data)
    return _c("kv", title=title, items=[[str(k), jsonable(v)] for k, v in items])


def html(content: str) -> Component:
    """Raw (sanitised) HTML. Prefer :func:`markdown` where possible."""
    return _c("html", html=str(content))


def divider() -> Component:
    return _c("divider")


def progress(value: float, label: str | None = None, kind: str | None = None) -> Component:
    """``value`` in [0, 1]."""
    return _c("progress", value=float(value), label=label, kind=kind)


def outcome(values: dict[str, Any], utility: float | None = None, label: str | None = None) -> Component:
    """A compact outcome card (issue → value chips plus an optional utility)."""
    return _c("outcome", values=jsonable(values), utility=utility, label=label)


# -- plots & tables ---------------------------------------------------------
def plot(fig: Any, *, height: int | None = None, key: str | None = None) -> Component:
    """A Plotly figure (``plotly.graph_objects.Figure`` or a figure dict)."""
    if hasattr(fig, "to_json"):
        spec = json.loads(fig.to_json())
    else:
        spec = jsonable(fig)
    return _c("plot", figure=spec, height=height, key=key)


def table(
    rows: Iterable[dict[str, Any]] | Any,
    columns: Sequence[str] | None = None,
    *,
    on_select: str | None = None,
    page_size: int = 25,
    formats: dict[str, str] | None = None,
    selected: int | None = None,
    max_height: int | None = None,
    searchable: bool = False,
    sortable: bool = True,
    dense: bool = True,
) -> Component:
    """A data table. ``rows`` may be a list of dicts or a pandas DataFrame.

    ``formats`` maps a column to ``"percent"``, ``"float"``, ``"int"`` or
    ``"text"``.
    """
    try:
        import pandas as pd

        if isinstance(rows, pd.DataFrame):
            if columns is None:
                columns = [str(c) for c in rows.columns]
            rows = rows.to_dict(orient="records")
    except Exception:  # pragma: no cover
        pass
    rows = [{str(k): jsonable(v) for k, v in r.items()} for r in rows]  # type: ignore
    if columns is None:
        cols: list[str] = []
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        columns = cols
    return _c(
        "table",
        rows=rows,
        columns=list(columns),
        on_select=on_select,
        page_size=page_size,
        formats=formats,
        selected=selected,
        max_height=max_height,
        searchable=searchable,
        sortable=sortable,
        dense=dense,
    )


# -- inputs -----------------------------------------------------------------
def _options(options: Any) -> list[dict[str, Any]]:
    if isinstance(options, dict):
        return [{"label": str(k), "value": jsonable(v)} for k, v in options.items()]
    out = []
    for o in options:
        if isinstance(o, dict) and "value" in o:
            out.append({"label": str(o.get("label", o["value"])), "value": jsonable(o["value"])})
        else:
            out.append({"label": str(o), "value": jsonable(o)})
    return out


def button(
    label: str,
    action: str,
    *,
    payload: dict[str, Any] | None = None,
    variant: str = "secondary",
    icon: str | None = None,
    disabled: bool = False,
    full: bool = False,
    tooltip: str | None = None,
) -> Component:
    """``variant``: primary | secondary | success | danger | ghost.
    ``icon``: a lucide icon name in kebab case (e.g. ``"sparkles"``)."""
    return _c(
        "button",
        label=label,
        action=action,
        payload=jsonable(payload or {}),
        variant=variant,
        icon=icon,
        disabled=disabled,
        full=full,
        tooltip=tooltip,
    )


def select(name: str, options: Any, value: Any = None, *, label: str | None = None, disabled: bool = False) -> Component:
    return _c("select", name=name, options=_options(options), value=jsonable(value), label=label, disabled=disabled)


def multiselect(name: str, options: Any, value: Sequence[Any] = (), *, label: str | None = None) -> Component:
    return _c("multiselect", name=name, options=_options(options), value=jsonable(list(value)), label=label)


def radio(name: str, options: Any, value: Any = None, *, label: str | None = None) -> Component:
    """A segmented control."""
    return _c("radio", name=name, options=_options(options), value=jsonable(value), label=label)


def slider(
    name: str,
    min: float,
    max: float,
    value: float,
    *,
    step: float = 1,
    label: str | None = None,
    suffix: str | None = None,
) -> Component:
    return _c("slider", name=name, min=min, max=max, value=jsonable(value), step=step, label=label, suffix=suffix)


def number(name: str, value: float | None, *, min: float | None = None, max: float | None = None,
           step: float | None = None, label: str | None = None) -> Component:
    return _c("number", name=name, value=jsonable(value), min=min, max=max, step=step, label=label)


def checkbox(name: str, value: bool, *, label: str | None = None) -> Component:
    return _c("checkbox", name=name, value=bool(value), label=label)


def switch(name: str, value: bool, *, label: str | None = None) -> Component:
    return _c("switch", name=name, value=bool(value), label=label)


def text(name: str, value: str = "", *, label: str | None = None, placeholder: str | None = None) -> Component:
    return _c("textinput", name=name, value=value, label=label, placeholder=placeholder)


def textarea(name: str, value: str = "", *, label: str | None = None, placeholder: str | None = None, rows: int = 3) -> Component:
    return _c("textarea", name=name, value=value, label=label, placeholder=placeholder, rows=rows)


# -- layout -----------------------------------------------------------------
def row(*children: Component | None, gap: int = 3, wrap: bool = True, align: str | None = None) -> Component:
    return _c("row", children=[c for c in children if c], gap=gap, wrap=wrap, align=align)


def column(*children: Component | None, gap: int = 3) -> Component:
    return _c("column", children=[c for c in children if c], gap=gap)


def grid(*children: Component | None, cols: int = 2, gap: int = 3) -> Component:
    """Responsive grid (collapses to one column on narrow panes)."""
    return _c("grid", children=[c for c in children if c], cols=cols, gap=gap)


def card(*children: Component | None, title: str | None = None, collapsible: bool = False,
         collapsed: bool = False) -> Component:
    return _c("card", title=title, children=[c for c in children if c], collapsible=collapsible, collapsed=collapsed)
