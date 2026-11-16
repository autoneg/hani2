"""Connects sessions to browser tabs over WebSockets.

Thread-safe: sessions call :meth:`Hub.push`, :meth:`Hub.push_state` and
:meth:`Hub.tool_changed` from any thread; delivery happens on the server's
event loop. State pushes and tool re-renders are coalesced, so a burst of
changes produces one message.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import traceback
from typing import Any

from hani2.tools.ui import jsonable


def _dumps(msg: dict[str, Any]) -> str:
    """JSON for the browser: NaN/inf are not valid JSON, so sanitise everything."""
    return json.dumps(jsonable(msg), allow_nan=False)


class Hub:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.sessions: dict[str, Any] = {}
        self._sockets: dict[str, set[Any]] = {}
        self._lock = threading.RLock()
        self._state_pending: set[str] = set()
        self._tools_pending: dict[str, set[str]] = {}

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    # -- sessions -----------------------------------------------------------
    def get(self, sid: str):
        return self.sessions.get(sid)

    def add(self, session) -> None:
        with self._lock:
            self.sessions[session.sid] = session

    def remove(self, sid: str) -> None:
        with self._lock:
            s = self.sessions.pop(sid, None)
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
        try:
            text = _dumps(msg)
        except Exception:
            traceback.print_exc()
            return
        self._call(self._send, sid, text)

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
            await self._send(sid, _dumps({"type": "state", "state": snap}))
        except Exception:
            traceback.print_exc()

    def tool_changed(self, sid: str, tid: str) -> None:
        with self._lock:
            pending = self._tools_pending.setdefault(sid, set())
            if tid in pending:
                return
            pending.add(tid)
        self._call(self._flush_tool, sid, tid)

    async def _flush_tool(self, sid: str, tid: str) -> None:
        await asyncio.sleep(0.05)
        with self._lock:
            self._tools_pending.get(sid, set()).discard(tid)
        s = self.sessions.get(sid)
        if s is None or not self._sockets.get(sid):
            return
        try:
            view = await asyncio.get_running_loop().run_in_executor(None, s.render_tool, tid)
            if view is not None:
                await self._send(sid, _dumps({"type": "tool", **view}))
        except Exception:
            traceback.print_exc()
