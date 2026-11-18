"""Turn a tool's components into text the Assistant (or an LLM) can read.

:func:`describe_components` walks the declarative components returned by
``Tool.view()`` and writes what a person would see: text, numbers, the first
rows of tables, a short summary of each chart, and the controls with the
names to use with ``use_tool``. Output is capped so a large tool never floods
the model's context.
"""

from __future__ import annotations

from typing import Any

__all__ = ["describe_components", "controls_of", "INPUT_TYPES"]

INPUT_TYPES = ("select", "multiselect", "radio", "slider", "number", "checkbox", "switch", "textinput", "textarea")


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmt(x) for x in v[:12]) + (", …" if len(v) > 12 else "") + "]"
    return str(v)


def _plot_summary(fig: dict[str, Any]) -> list[str]:
    layout = fig.get("layout") or {}
    title = layout.get("title")
    if isinstance(title, dict):
        title = title.get("text")
    out = [f"Chart{': ' + str(title) if title else ''}"]
    for ax in ("xaxis", "yaxis"):
        t = (layout.get(ax) or {}).get("title")
        if isinstance(t, dict):
            t = t.get("text")
        if t:
            out.append(f"  {ax[0]} axis: {t}")
    for tr in (fig.get("data") or [])[:8]:
        kind = tr.get("type") or "scatter"
        name = tr.get("name") or ""
        if kind == "pie":
            labels, values = tr.get("labels") or [], tr.get("values") or []
            total = sum(float(v) for v in values if isinstance(v, (int, float))) or 1.0
            parts = [f"{lab} {float(val) / total:.0%}" for lab, val in zip(labels, values) if isinstance(val, (int, float))]
            out.append(f"  pie {name}: " + ", ".join(parts[:15]))
            continue
        x, y = tr.get("x"), tr.get("y")
        if isinstance(x, dict) or isinstance(y, dict):  # plotly binary arrays
            out.append(f"  {kind} {name}".rstrip())
            continue
        n = len(x or y or [])
        line = f"  {kind} {name}".rstrip() + f" ({n} points)"
        if n and n <= 12:
            pts = list(zip(x or range(n), y or [None] * n))
            line += ": " + "; ".join(f"{_fmt(a)} → {_fmt(b)}" for a, b in pts)
        elif n:
            ys = [v for v in (y or []) if isinstance(v, (int, float))]
            if ys:
                line += f", y from {_fmt(min(ys))} to {_fmt(max(ys))}, last {_fmt(ys[-1])}"
        out.append(line)
    return out


def _walk(c: Any, out: list[str], depth: int, max_rows: int) -> None:
    if not isinstance(c, dict):
        return
    t = c.get("type")
    pad = "  " * depth
    if t in ("markdown", "text", "heading"):
        txt = str(c.get("text") or "").strip()
        if txt:
            out.append(pad + txt)
    elif t == "alert":
        out.append(pad + f"[{c.get('kind', 'info')}] " + (f"{c['title']}: " if c.get("title") else "") + str(c.get("text") or ""))
    elif t == "badge":
        out.append(pad + f"[{c.get('text')}]")
    elif t == "stat":
        out.append(pad + f"{c.get('label')}: {_fmt(c.get('value'))}" + (f" ({c['hint']})" if c.get("hint") else ""))
    elif t == "kv":
        if c.get("title"):
            out.append(pad + str(c["title"]))
        for k, v in c.get("items") or []:
            out.append(pad + f"{k}: {_fmt(v)}")
    elif t == "progress":
        out.append(pad + f"{c.get('label') or 'progress'}: {_fmt(c.get('value'))}")
    elif t == "outcome":
        vals = ", ".join(f"{k}={_fmt(v)}" for k, v in (c.get("values") or {}).items())
        out.append(pad + (f"{c['label']}: " if c.get("label") else "Offer: ") + vals
                   + (f" (utility {_fmt(c['utility'])})" if c.get("utility") is not None else ""))
    elif t == "plot":
        out.extend(pad + line for line in _plot_summary(c.get("figure") or {}))
    elif t == "table":
        rows, cols = c.get("rows") or [], c.get("columns") or []
        head = f"Table ({len(rows)} rows)"
        if c.get("on_select"):
            head += f" — select a row with use_tool(action={c['on_select']!r}, row=<index>)"
        out.append(pad + head)
        if cols:
            out.append(pad + "  " + " | ".join(map(str, cols)))
        for i, r in enumerate(rows[:max_rows]):
            out.append(pad + f"  {i}: " + " | ".join(_fmt(r.get(k)) for k in cols))
        if len(rows) > max_rows:
            out.append(pad + f"  … {len(rows) - max_rows} more rows")
    elif t in INPUT_TYPES:
        desc = f"Input {c.get('name')!r}" + (f" ({c['label']})" if c.get("label") else "") + f" = {_fmt(c.get('value'))}"
        if c.get("options"):
            desc += "; options: " + ", ".join(_fmt(o.get("value")) for o in c["options"][:20])
        if t in ("slider", "number") and (c.get("min") is not None or c.get("max") is not None):
            desc += f"; range {_fmt(c.get('min'))}–{_fmt(c.get('max'))}"
        out.append(pad + desc)
    elif t == "button":
        out.append(pad + f"Button {c.get('label')!r} → action {c.get('action')!r}" + (" (disabled)" if c.get("disabled") else ""))
    elif t in ("card", "row", "column", "grid", "stats", "tabs", "section"):
        if c.get("title"):
            out.append(pad + f"## {c['title']}")
        for ch in c.get("children") or []:
            _walk(ch, out, depth + (1 if t == "card" else 0), max_rows)
        for tab in c.get("tabs") or []:
            if isinstance(tab, dict):
                out.append(pad + f"## {tab.get('label') or tab.get('title') or ''}")
                for ch in tab.get("children") or []:
                    _walk(ch, out, depth + 1, max_rows)
    else:
        for ch in c.get("children") or []:
            _walk(ch, out, depth, max_rows)


def describe_components(components: list[Any], *, max_chars: int = 4000, max_rows: int = 10) -> str:
    """A plain-text rendering of ``components``, at most ``max_chars`` long."""
    out: list[str] = []
    for c in components or []:
        _walk(c, out, 0, max_rows)
    text = "\n".join(line for line in out if line.strip())
    if len(text) > max_chars:
        text = text[: max_chars - 20].rstrip() + "\n… (truncated)"
    return text


def controls_of(components: list[Any]) -> dict[str, Any]:
    """The inputs, buttons and selectable tables in ``components``:
    ``{"inputs": {name: component}, "actions": {action: component},
    "tables": {on_select_action: table component}}``."""
    found: dict[str, Any] = {"inputs": {}, "actions": {}, "tables": {}}

    def walk(c: Any) -> None:
        if not isinstance(c, dict):
            return
        t = c.get("type")
        if t in INPUT_TYPES and c.get("name"):
            found["inputs"][str(c["name"])] = c
        elif t == "button" and c.get("action"):
            found["actions"][str(c["action"])] = c
        elif t == "table" and c.get("on_select"):
            found["tables"][str(c["on_select"])] = c
        for ch in c.get("children") or []:
            walk(ch)
        for tab in c.get("tabs") or []:
            if isinstance(tab, dict):
                for ch in tab.get("children") or []:
                    walk(ch)

    for c in components or []:
        walk(c)
    return found
