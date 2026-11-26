"""Server-side tool layout: which tools exist, where they are and whether they
are visible / enabled. Both the participant's buttons and the Assistant
go through this controller, so their behaviour cannot drift apart."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from hani2.session import NegotiationSession
    from hani2.tools.base import Tool

PANES = ("upper", "lower", "side")


class ToolController:
    def __init__(self, session: "NegotiationSession"):
        self.session = session

    # -- lookup ----------------------------------------------------------
    @property
    def tools(self) -> list["Tool"]:
        """The tools on offer this round (a tool can depend on the information split)."""
        available = getattr(self.session, "tool_available", None)
        return [t for t in self.session.tools if available is None or available(t)]

    def find(self, name: str) -> "Tool | None":
        key = str(name or "").strip().lower()
        for t in self.tools:
            if t.name.lower() == key:
                return t
        for t in self.tools:
            if key and (key in t.name.lower() or t.name.lower() in key):
                return t
        return None

    def list_tools(self) -> list[dict[str, Any]]:
        out = []
        for t in self.tools:
            st = self.session.tool_state(t)
            out.append(
                dict(
                    name=t.name,
                    description=t.description,
                    pane=st["pane"],
                    position=self.pane_tools(st["pane"]).index(t) if t in self.pane_tools(st["pane"]) else None,
                    visible=st["visible"],
                    enabled=st["enabled"],
                    permanent=t.permanent,
                    active=self.session.active_tabs.get(st["pane"]) == t.name,
                    **({"private": True} if getattr(self.session, "tool_private_to_human", lambda _t: False)(t) else {}),
                )
            )
        return out

    def _bare(self, res: dict) -> dict:
        """Add a note to a successful result when the bare view shows no tools at all."""
        if res.get("ok") and (getattr(self.session, "layout", None) or {}).get("view") == "bare":
            locked = getattr(self.session, "view_locked", lambda: False)()
            res["note"] = ("the bare view shows no tools; the study fixes the view, so the participant will not see it"
                           if locked else "the bare view shows no tools; switch the view (set_layout) to show it")
        return res

    def pane_tools(self, pane: str) -> list["Tool"]:
        items = [t for t in self.tools if self.session.tool_state(t)["pane"] == pane]
        return sorted(items, key=lambda t: self.session.tool_state(t)["order"])

    # -- mutations ---------------------------------------------------------
    def set_tool_enabled(self, name: str, enabled: bool, allow_permanent: bool = False) -> dict:
        t = self.find(name)
        if t is None:
            return {"ok": False, "error": f"no tool named {name!r}"}
        if t.permanent and not enabled and not allow_permanent:
            return {"ok": False, "error": f"{t.name} is permanent"}
        self.session.tool_state(t)["enabled"] = bool(enabled)
        t.enabled = bool(enabled)
        if enabled:
            t.refresh()
        self.session.push_state()
        return {"ok": True, "tool": t.name, "enabled": bool(enabled)}

    def set_tool_visible(self, name: str, visible: bool, allow_permanent: bool = False) -> dict:
        t = self.find(name)
        if t is None:
            return {"ok": False, "error": f"no tool named {name!r}"}
        if t.permanent and not visible and not allow_permanent:
            return {"ok": False, "error": f"{t.name} is permanent"}
        st = self.session.tool_state(t)
        st["visible"] = bool(visible)
        pane = st["pane"]
        if visible:
            self.session.active_tabs[pane] = t.name
            t.refresh()
        elif self.session.active_tabs.get(pane) == t.name:
            others = [x for x in self.pane_tools(pane) if self.session.tool_state(x)["visible"]]
            self.session.active_tabs[pane] = others[0].name if others else None
        self.session.push_state()
        return self._bare({"ok": True, "tool": t.name, "visible": bool(visible)})

    def move_tool(self, name: str, position: int | None = None, pane: str | None = None) -> dict:
        t = self.find(name)
        if t is None:
            return {"ok": False, "error": f"no tool named {name!r}"}
        st = self.session.tool_state(t)
        if pane is not None:
            if pane not in PANES:
                return {"ok": False, "error": f"pane must be one of {PANES}"}
            st["pane"] = pane
        items = [x for x in self.pane_tools(st["pane"]) if x is not t]
        pos = len(items) if position is None else max(0, min(int(position), len(items)))
        items.insert(pos, t)
        for i, x in enumerate(items):
            self.session.tool_state(x)["order"] = i
        st["visible"] = True
        self.session.active_tabs[st["pane"]] = t.name
        self.session.push_state()
        return self._bare({"ok": True, "tool": t.name, "pane": st["pane"], "position": pos})

    def focus_tool(self, name: str) -> dict:
        """Bring a tool's tab to the front (showing and enabling it)."""
        t = self.find(name)
        if t is None:
            return {"ok": False, "error": f"no tool named {name!r}"}
        st = self.session.tool_state(t)
        st["visible"] = True
        if not st["enabled"]:
            st["enabled"] = True
            t.enabled = True
        self.session.active_tabs[st["pane"]] = t.name
        # views that show every pane in one tab strip (tablet, phone, simple) follow "all"
        self.session.active_tabs["all"] = t.name
        t.refresh()
        self.session.push_state()
        return self._bare({"ok": True, "tool": t.name, "pane": st["pane"]})

    def restore_all(self) -> list[str]:
        names = []
        for t in self.tools:
            st = self.session.tool_state(t)
            if not st["visible"]:
                st["visible"] = True
                names.append(t.name)
        self.session.push_state()
        return names

    # Helpers used by tool buttons
    def move_obj_to_pane(self, tool: "Tool", pane: str) -> dict:
        return self.move_tool(tool.name, pane=pane)

    def hide_obj(self, tool: "Tool") -> dict:
        return self.set_tool_visible(tool.name, False)
