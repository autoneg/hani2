"""Event tracking: an append-only SQLite log of everything that happens.

Events are typed (``EventType``). The database lives at
``<results root>/events.db``. Logging is best-effort and never raises.
Set ``HANI2_EVENTS=0`` to disable it.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from hani2.config import results_root

__all__ = ["EventType", "log_event", "query_events", "event_summary", "start_session_record", "end_session_record"]


class EventType(str, Enum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    SCENARIO_LOADED = "scenario_loaded"
    SCENARIO_STARTED = "scenario_started"
    OFFER_MADE = "offer_made"
    OFFER_ACCEPTED = "offer_accepted"
    OFFER_REJECTED = "offer_rejected"
    NEGOTIATION_ENDED = "negotiation_ended"
    COUNTER_OFFER = "counter_offer"
    TOOL_OPENED = "tool_opened"
    TOOL_CLOSED = "tool_closed"
    TOOL_INTERACTION = "tool_interaction"
    BUTTON_CLICKED = "button_clicked"
    PAGE_VIEW = "page_view"
    TAB_CHANGED = "tab_changed"
    MODAL_OPENED = "modal_opened"
    MODAL_CLOSED = "modal_closed"
    PREFERENCE_VIEWED = "preference_viewed"
    PLOT_VIEWED = "plot_viewed"
    RESULTS_VIEWED = "results_viewed"
    SUPPORT_AGENT = "support_agent"
    ERROR = "error"
    WARNING = "warning"


_LOCK = threading.Lock()
_CONN: dict[str, sqlite3.Connection] = {}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT, user TEXT, experiment TEXT,
    event_type TEXT NOT NULL, timestamp TEXT NOT NULL,
    component TEXT, action TEXT, value TEXT,
    scenario_id TEXT, round_number INTEGER, utility_value REAL, duration_ms REAL
);
CREATE INDEX IF NOT EXISTS ix_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS ix_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS ix_events_user ON events(user);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, user TEXT, experiment TEXT, mode TEXT,
    start_time TEXT, end_time TEXT, ip TEXT, user_agent TEXT
);
"""


def _enabled() -> bool:
    return os.environ.get("HANI2_EVENTS", "1").lower() not in ("0", "false", "no", "off")


def _conn() -> sqlite3.Connection:
    path = str(results_root() / "events.db")
    c = _CONN.get(path)
    if c is None:
        c = sqlite3.connect(path, check_same_thread=False, timeout=10)
        c.executescript(_SCHEMA)
        c.commit()
        _CONN[path] = c
    return c


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(
    session_id: str | None,
    event_type: EventType | str,
    *,
    user: str | None = None,
    component: str | None = None,
    action: str | None = None,
    value: Any = None,
    scenario_id: str | None = None,
    round_number: int | None = None,
    utility_value: float | None = None,
    duration_ms: float | None = None,
) -> None:
    if not _enabled():
        return
    try:
        from hani2.config import experiment_name

        et = event_type.value if isinstance(event_type, EventType) else str(event_type)
        v = None if value is None else json.dumps(value, default=str)
        with _LOCK:
            c = _conn()
            c.execute(
                "INSERT INTO events (session_id,user,experiment,event_type,timestamp,component,action,value,"
                "scenario_id,round_number,utility_value,duration_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (session_id, user, experiment_name(), et, _now(), component, action, v, scenario_id,
                 round_number, utility_value, duration_ms),
            )
            c.commit()
    except Exception as e:  # pragma: no cover - never break the app
        print(f"[hani2] event logging failed: {e}")


def start_session_record(sid: str, user: str, mode: str, ip: str | None = None, user_agent: str | None = None) -> None:
    if not _enabled():
        return
    try:
        from hani2.config import experiment_name

        with _LOCK:
            c = _conn()
            c.execute(
                "INSERT OR REPLACE INTO sessions (id,user,experiment,mode,start_time,ip,user_agent) VALUES (?,?,?,?,?,?,?)",
                (sid, user, experiment_name(), mode, _now(), ip, user_agent),
            )
            c.commit()
    except Exception as e:  # pragma: no cover
        print(f"[hani2] session logging failed: {e}")


def end_session_record(sid: str) -> None:
    if not _enabled():
        return
    try:
        with _LOCK:
            c = _conn()
            c.execute("UPDATE sessions SET end_time=? WHERE id=?", (_now(), sid))
            c.commit()
    except Exception:  # pragma: no cover
        pass


def query_events(
    *,
    user: str | None = None,
    session_id: str | None = None,
    event_types: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> list[dict]:
    where, args = [], []
    if user:
        where.append("user = ?")
        args.append(user)
    if session_id:
        where.append("session_id = ?")
        args.append(session_id)
    if event_types:
        where.append(f"event_type IN ({','.join('?' * len(event_types))})")
        args.extend(event_types)
    if since:
        where.append("timestamp >= ?")
        args.append(since)
    if until:
        where.append("timestamp <= ?")
        args.append(until)
    sql = "SELECT * FROM events" + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    with _LOCK:
        c = _conn()
        c.row_factory = sqlite3.Row
        rows = [dict(r) for r in c.execute(sql, args).fetchall()]
        c.row_factory = None
    return rows


def query_sessions(limit: int = 500) -> list[dict]:
    with _LOCK:
        c = _conn()
        c.row_factory = sqlite3.Row
        rows = [dict(r) for r in c.execute("SELECT * FROM sessions ORDER BY start_time DESC LIMIT ?", (limit,))]
        c.row_factory = None
    return rows


def event_summary() -> dict:
    with _LOCK:
        c = _conn()
        by_type = dict(c.execute("SELECT event_type, COUNT(*) FROM events GROUP BY event_type").fetchall())
        by_hour = c.execute(
            "SELECT substr(timestamp,1,13) AS h, COUNT(*) FROM events GROUP BY h ORDER BY h DESC LIMIT 168"
        ).fetchall()
        users = [r[0] for r in c.execute("SELECT DISTINCT user FROM events WHERE user IS NOT NULL").fetchall()]
        n_sessions = c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        n_events = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    return {
        "by_type": by_type,
        "by_hour": [{"hour": h, "count": n} for h, n in reversed(by_hour)],
        "users": users,
        "n_sessions": n_sessions,
        "n_events": n_events,
    }
