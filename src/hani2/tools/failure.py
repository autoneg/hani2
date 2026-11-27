"""What happens when a tool fails.

A tool is code that HANI2 did not write (a tools folder, ``hani2 --tools``,
``tools.extra``, an entry point, the library), so it may raise anywhere or never
return. A failing tool must not break the session, the negotiation, the other
tools or the page: the session calls every tool method through
:meth:`hani2.session.NegotiationSession.guard_tool`, which records the failure on
the tool and shows it **in that tool's own pane** only:

* a tool that fails to **start** (its constructor or :meth:`Tool.init` raises)
  shows the failure view for the rest of the session;
* a tool that fails to **render** (:meth:`Tool.view` raises, or takes longer than
  ``tools.render_timeout`` seconds) shows the failure view until a later render
  succeeds;
* a tool that fails in a **hook**, an input or a button shows its normal view under
  an error banner until the same call succeeds again.

Admins see the error type, the message and the traceback; participants see only
that the tool is not working right now.

External tools are always guarded. Built-in tools (classes defined in the
``hani2`` package) are guarded too unless env.json → ``tools.isolate_builtin``
is ``false``; then their errors surface exactly as they did before (printed, or
raised for a render), which helps when debugging HANI2 itself.
"""

from __future__ import annotations

import time
import traceback
from typing import Any

from hani2.config import get_env
from hani2.tools import ui
from hani2.tools.base import Tool

__all__ = ["FailedTool", "is_builtin", "isolate_builtin", "render_timeout", "make_failure", "failure_view",
           "failure_banner", "START", "RENDER"]

#: failures of these calls mean the tool never started: it stays failed
START = ("create", "init")
#: failures of a render (an exception or a timeout): cleared by the next good render
RENDER = ("render", "timeout")
DEFAULT_RENDER_TIMEOUT = 20.0


def is_builtin(cls: type) -> bool:
    """Whether a tool class is HANI2's own: defined in the ``hani2`` package
    (the built-in tools and HANI2's own helper classes). Tools from a tools folder
    (imported as ``hani2_user_tools.*``), ``tools.extra``, entry points, the library
    and :func:`~hani2.tools.register_tool` are external, even when they subclass a
    built-in tool."""
    mod = str(getattr(cls, "__module__", "") or "")
    return mod == "hani2" or mod.startswith("hani2.")


def isolate_builtin() -> bool:
    """env.json → ``tools.isolate_builtin`` (default ``true``): guard built-in tools too."""
    v = get_env("tools.isolate_builtin", True)
    if isinstance(v, str):
        return v.strip().lower() not in ("false", "0", "no", "off")
    return bool(v)


def render_timeout() -> float | None:
    """env.json → ``tools.render_timeout``: seconds a guarded tool may take to render
    (default 20); ``0`` or less means no limit."""
    try:
        v = float(get_env("tools.render_timeout", DEFAULT_RENDER_TIMEOUT))
    except (TypeError, ValueError):
        v = DEFAULT_RENDER_TIMEOUT
    return v if v > 0 else None


def make_failure(where: str, exc: BaseException | None = None, *, message: str | None = None,
                 error_type: str | None = None) -> dict[str, Any]:
    """The record kept in the tool's state: ``{where, error_type, message, traceback, at}``."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc is not None else ""
    return dict(where=str(where), error_type=error_type or (type(exc).__name__ if exc is not None else "Error"),
                message=message if message is not None else (str(exc) if exc is not None else ""),
                traceback=tb, at=time.time())


def _what(f: dict[str, Any]) -> str:
    where = f.get("where", "")
    if where in START:
        return "failed to start"
    if where == "render":
        return "failed to render"
    if where == "timeout":
        return "took too long to render"
    return f"failed in `{where}`"


def _details(f: dict[str, Any]) -> list[ui.Component]:
    out: list[ui.Component] = []
    if f.get("traceback"):
        out.append(ui.card(ui.markdown("```text\n" + f["traceback"].rstrip() + "\n```"), title="Traceback",
                           collapsible=True, collapsed=True))
    return out


def failure_view(name: str, f: dict[str, Any] | None, admin: bool) -> list[ui.Component]:
    """What the pane of a tool that failed to start or to render shows."""
    f = f or make_failure("render", message="unknown error")
    if not admin:
        return [ui.alert("This tool is not working right now. Everything else on the page works as usual.",
                         "error", title=f"{name} is not available")]
    msg = f"**{f.get('error_type', 'Error')}**: {f.get('message') or '(no message)'}"
    return [ui.alert(f"`{name}` {_what(f)}.\n\n{msg}", "error", title=f"{name} is not working"),
            *_details(f),
            ui.text_block("Participants only see that this tool is not working right now; the session and the "
                          "other tools carry on.", muted=True)]


def failure_banner(name: str, f: dict[str, Any], admin: bool) -> list[ui.Component]:
    """Shown above the normal view of a tool that failed in a hook, an input or a button."""
    if not admin:
        return [ui.alert("Something went wrong in this tool; what it shows may be out of date.", "error")]
    msg = f"**{f.get('error_type', 'Error')}**: {f.get('message') or '(no message)'}"
    return [ui.alert(f"`{name}` {_what(f)}.\n\n{msg}", "error", title=f"{name} had an error"), *_details(f)]


class FailedTool(Tool):
    """Stands in for a tool whose constructor raised: it keeps the tool's name,
    tab and place and shows the failure in its pane."""

    icon = "triangle-alert"

    def __init__(self, session_state: dict[str, Any], *, name: str, cls: type | None = None,
                 failure: dict[str, Any] | None = None, enabled: bool | None = None):
        super().__init__(session_state, enabled=enabled)
        self.name = name
        self.failed_class = cls
        self.failure = failure or make_failure("create", message="the tool could not be created")
        for attr in ("description", "icon", "help"):
            try:
                v = getattr(cls, attr, None)
                if isinstance(v, str) and v:
                    setattr(self, attr, v)
            except Exception:  # noqa: BLE001
                pass

    def view(self) -> list[ui.Component]:
        return failure_view(self.name, self.failure, admin=False)
