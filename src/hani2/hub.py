"""Connects sessions to browser tabs over WebSockets.

Thread-safe: sessions call :meth:`Hub.push`, :meth:`Hub.push_state` and
:meth:`Hub.tool_changed` from any thread; delivery happens on the server's
event loop. State pushes and tool re-renders are coalesced, so a burst of
changes produces one message.

Tool views are rendered off the event loop in their own thread pool, so a slow
tool never delays state pushes or other sessions. Only tools the participant
can currently see are rendered; a hidden tool is rendered when its tab is
opened. A tool that changes while it is being rendered is rendered once more
afterwards (never twice at the same time).

A guarded tool (see :mod:`hani2.tools.failure`) gets ``tools.render_timeout``
seconds to render, in a thread of its own: a tool that takes longer shows that it
failed and is not rendered again until that render returns, so a hanging tool
never holds up the other tools or sessions.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from hani2.tools.ui import jsonable


def _dumps(msg: dict[str, Any]) -> str:
    """JSON for the browser: NaN/inf are not valid JSON, so sanitise everything."""
    return json.dumps(jsonable(msg), allow_nan=False)


TOOL_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="hani2-tool")
#: how many time-boxed tool renders run at once (a render that took too long no longer counts)
TOOL_RENDER_SLOTS = 8


class Hub:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.sessions: dict[str, Any] = {}
        self._sockets: dict[str, set[Any]] = {}
        self._lock = threading.RLock()
        self._create_locks: dict[str, threading.Lock] = {}  # one per sid: serialises get-or-create
        self._state_pending: set[str] = set()
        self._tools_pending: dict[str, set[str]] = {}
        self._tools_rendering: set[tuple[str, str]] = set()
        self._tools_again: set[tuple[str, str]] = set()
        self._tools_sent: set[tuple[str, str]] = set()
        self._render_slots: tuple[asyncio.AbstractEventLoop, asyncio.Semaphore] | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Deliver on ``loop`` from now on. Pushes queued on a previous loop
        will never run, so forget them (otherwise they would block new ones)."""
        with self._lock:
            self.loop = loop
            self._state_pending.clear()
            self._tools_pending.clear()
            self._tools_rendering.clear()
            self._tools_again.clear()
            self._tools_sent.clear()

    # -- sessions -----------------------------------------------------------
    def get(self, sid: str):
        return self.sessions.get(sid)

    def add(self, session) -> None:
        with self._lock:
            self.sessions[session.sid] = session

    def get_or_create(self, sid: str, factory, *, fresh: bool = False, init=None):
        """The session ``sid``, made with ``factory()`` (then ``init(session)``) if it is missing.

        Atomic per sid: concurrent calls for one sid get the same session, and none
        gets it before ``init`` has finished. Calls for other sids are not blocked.
        ``fresh=True`` removes an existing session first. Returns ``(session, created)``.
        """
        with self._lock:
            lock = self._create_locks.setdefault(sid, threading.Lock())
        with lock:
            s = self.sessions.get(sid)
            if s is not None and fresh:
                self.remove(sid)
                s = None
            if s is not None:
                return s, False
            s = factory()
            self.add(s)
            if init is not None:
                init(s)
            return s, True

    def remove(self, sid: str) -> None:
        with self._lock:
            s = self.sessions.pop(sid, None)
            self._tools_sent = {k for k in self._tools_sent if k[0] != sid}
            self._tools_pending.pop(sid, None)
        if s is not None:
            try:
                s.close()
            except Exception:
                pass

    def gc(self, max_idle: float = 6 * 3600) -> int:
        now = time.time()
        stale = [sid for sid, s in list(self.sessions.items())
                 if not self._sockets.get(sid) and now - s.last_seen > max_idle and s.phase != "running"]
        for sid in stale:
            self.remove(sid)
        return len(stale)

    # -- sockets --------------------------------------------------------------
    def connect(self, sid: str, ws) -> None:
        with self._lock:
            self._sockets.setdefault(sid, set()).add(ws)
            # a new tab has no tool views yet: send each again when it is shown
            self._tools_sent = {k for k in self._tools_sent if k[0] != sid}

    def disconnect(self, sid: str, ws) -> None:
        with self._lock:
            self._sockets.get(sid, set()).discard(ws)

    def n_connections(self, sid: str) -> int:
        return len(self._sockets.get(sid, ()))

    async def _send(self, sid: str, text: str) -> None:
        for ws in list(self._sockets.get(sid, ())):
            try:
                await ws.send_text(text)
            except Exception:
                self.disconnect(sid, ws)

    def _call(self, coro_fn, *args) -> None:
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            loop.create_task(coro_fn(*args))
        else:
            asyncio.run_coroutine_threadsafe(coro_fn(*args), loop)

    # -- public API used by sessions --------------------------------------------
    def push(self, sid: str, msg: dict[str, Any]) -> None:
        if self.sessions.get(sid) is not None and getattr(self.sessions[sid], "recorder", None) is not None:
            try:
                msg = jsonable(msg)  # a copy: the caller may change its lists before the loop sends
            except Exception:
                traceback.print_exc()
                return
            self._call(self._send_msg, sid, msg)  # recorded in send order on the loop
            return
        try:
            text = _dumps(msg)
        except Exception:
            traceback.print_exc()
            return
        self._call(self._send, sid, text)

    def _stamp(self, sid: str, msg: dict[str, Any]) -> dict[str, Any]:
        """Record an outgoing message and add its sequence number (``_seq``),
        which the browser echoes in its telemetry so a replay can line up
        what was on screen with what the participant did."""
        s = self.sessions.get(sid)
        r = getattr(s, "recorder", None)
        if r is None:
            return msg
        seq = r.outbound(msg)
        return {**msg, "_seq": seq}

    async def _send_msg(self, sid: str, msg: dict[str, Any]) -> None:
        try:
            text = _dumps(self._stamp(sid, msg))
        except Exception:
            traceback.print_exc()
            return
        await self._send(sid, text)

    def push_state(self, sid: str) -> None:
        with self._lock:
            if sid in self._state_pending:
                return
            self._state_pending.add(sid)
        self._call(self._flush_state, sid)

    async def _flush_state(self, sid: str) -> None:
        await asyncio.sleep(0.02)  # coalesce bursts
        with self._lock:
            self._state_pending.discard(sid)
        s = self.sessions.get(sid)
        if s is None or not self._sockets.get(sid):
            return
        try:
            snap = await asyncio.get_running_loop().run_in_executor(None, s.snapshot)
            await self._send(sid, _dumps(self._stamp(sid, {"type": "state", "state": snap})))
        except Exception:
            traceback.print_exc()
        self._render_newly_shown(s)

    def _render_newly_shown(self, s) -> None:
        """Render tools that became visible and changed (or were never sent)
        while hidden: a tab opened by the Assistant, a revealed tool, …"""
        names_fn = getattr(s, "shown_tool_names", None)
        if names_fn is None:
            return
        try:
            names = names_fn()
            for t in list(s.tools):
                if t.name not in names:
                    continue
                tid = s.tool_state(t)["id"]
                if getattr(t, "_dirty", False) or (s.sid, tid) not in self._tools_sent:
                    self.tool_changed(s.sid, tid)
        except Exception:
            traceback.print_exc()

    def tool_changed(self, sid: str, tid: str) -> None:
        s = self.sessions.get(sid)
        shown = getattr(s, "tool_is_shown", None)
        if shown is not None:
            try:
                if not shown(tid):
                    return  # rendered when its tab is opened
            except Exception:
                traceback.print_exc()
        key = (sid, tid)
        with self._lock:
            if key in self._tools_rendering:
                self._tools_again.add(key)
                return
            pending = self._tools_pending.setdefault(sid, set())
            if tid in pending:
                return
            pending.add(tid)
        self._call(self._flush_tool, sid, tid)

    async def render_tool_view(self, s, tid: str) -> dict[str, Any] | None:
        """``s.render_tool(tid)`` off the event loop. A guarded tool (one with a
        ``tools.render_timeout``) renders in a thread of its own and gets that many
        seconds; past them the session marks it hung and its failure view is returned."""
        loop = asyncio.get_running_loop()
        limit = getattr(s, "tool_render_timeout", None)
        timeout = limit(tid) if limit is not None else None
        if timeout is None:
            return await loop.run_in_executor(TOOL_EXECUTOR, s.render_tool, tid)
        if self._render_slots is None or self._render_slots[0] is not loop:
            self._render_slots = (loop, asyncio.Semaphore(TOOL_RENDER_SLOTS))
        timed_out = False

        def finish(fut: asyncio.Future, result: Any, error: BaseException | None) -> None:
            if timed_out:  # the render that took too long is back: it may be rendered again
                try:
                    s.tool_render_returned(tid)
                    self.tool_changed(s.sid, tid)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
            elif not fut.done():
                fut.set_exception(error) if error is not None else fut.set_result(result)

        async with self._render_slots[1]:
            fut = loop.create_future()

            def work() -> None:
                try:
                    result, error = s.render_tool(tid), None
                except BaseException as e:  # noqa: BLE001 - handed to the event loop
                    result, error = None, e
                try:
                    loop.call_soon_threadsafe(finish, fut, result, error)
                except RuntimeError:  # the loop is gone
                    pass

            threading.Thread(target=work, name="hani2-tool-render", daemon=True).start()
            try:
                return await asyncio.wait_for(fut, timeout)
            except asyncio.TimeoutError:
                timed_out = True
                return s.tool_render_timed_out(tid, timeout)

    async def _flush_tool(self, sid: str, tid: str) -> None:
        await asyncio.sleep(0.05)
        key = (sid, tid)
        with self._lock:
            self._tools_pending.get(sid, set()).discard(tid)
            if key in self._tools_rendering:
                self._tools_again.add(key)
                return
            self._tools_rendering.add(key)
        s = self.sessions.get(sid)
        try:
            if s is None or not self._sockets.get(sid):
                return
            view = await self.render_tool_view(s, tid)
            if view is not None:
                try:
                    msg = _dumps(self._stamp(sid, {"type": "tool", **view}))
                except Exception as e:  # noqa: BLE001 - a view that cannot be sent is the tool's failure
                    failed = getattr(s, "tool_view_unsendable", None)
                    view = failed(tid, e) if failed is not None else None
                    if view is None:
                        raise
                    msg = _dumps(self._stamp(sid, {"type": "tool", **view}))
                with self._lock:
                    self._tools_sent.add(key)
                await self._send(sid, msg)
        except Exception:
            traceback.print_exc()
        finally:
            with self._lock:
                self._tools_rendering.discard(key)
                again = key in self._tools_again
                self._tools_again.discard(key)
            if again:
                self.tool_changed(sid, tid)
