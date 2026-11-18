"""Helpers to run negotiations headlessly — for tests of your agents and tools.

Example::

    from hani2.testing import make_session

    s = make_session(agent_class="my_agent:MyAgent", opponent="BoulwareTBNegotiator")
    s.start()
    s.wait_for_turn()
    s.send_counter("Here is my offer")
    s.wait_for_turn()
    s.accept()
    s.wait_until_done()
    print(s.result)

Everything is written under a temporary ``HANI2_HOME`` unless you pass one.
"""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from typing import Any

from hani2.session import NegotiationSession


class _Collector:
    """A stand-in for the WebSocket hub that records what would be sent."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.state_pushes = 0

    def push(self, sid: str, msg: dict[str, Any]) -> None:
        self.messages.append(msg)

    def push_state(self, sid: str) -> None:
        self.state_pushes += 1

    def tool_changed(self, sid: str, tid: str) -> None:
        pass

    def of_type(self, kind: str) -> list[dict[str, Any]]:
        return [m for m in self.messages if m.get("type") == kind]


class TestSession(NegotiationSession):
    """A :class:`NegotiationSession` with waiting helpers."""

    __test__ = False  # not a pytest test class

    hub: _Collector

    def wait(self, predicate, timeout: float = 30.0, interval: float = 0.02) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if predicate():
                return True
            time.sleep(interval)
        return False

    def wait_for_turn(self, timeout: float = 30.0) -> bool:
        """Wait until it is the human's turn (or the negotiation ended)."""
        return self.wait(lambda: (self.is_my_turn() and not self.thinking) or self.phase not in ("running", "starting"), timeout)

    def wait_until_done(self, timeout: float = 60.0) -> bool:
        return self.wait(lambda: self.phase in ("ended", "questionnaire", "finished")
                         and not getattr(self, "_finishing", False), timeout)

    def wait_agent_idle(self, timeout: float = 30.0) -> bool:
        sa = self.support_agent
        if sa is None:
            return True
        time.sleep(0.05)
        return self.wait(lambda: not sa.busy and not self.agent_work_pending(), timeout)

    def play_counters(self, n: int, text: str | None = None) -> None:
        """Send ``n`` counter-offers (the current draft) as the human."""
        for _ in range(n):
            if not self.wait_for_turn() or self.phase != "running":
                return
            self.send_counter(text)
            time.sleep(0.05)


def make_session(
    *,
    user: str = "tester",
    mode: str = "main",
    opponent: str | None = None,
    agent_class: str | None = None,
    assistant_settings: dict[str, Any] | None = None,
    scenario_type: str | None = "Trade",
    n_steps: int | None = 20,
    time_limit: float | None = None,
    is_admin: bool = False,
    home: str | None = None,
    query: dict[str, Any] | None = None,
    load: bool = True,
    partner: str | None = "BoulwareTBNegotiator",
    support_settings: dict[str, Any] | None = None,
    study: Any = None,
) -> TestSession:
    """Create a headless session (and load a scenario).

    ``opponent`` is the opponent negotiator (default ``BoulwareTBNegotiator``).
    ``agent_class`` / ``assistant_settings`` configure the Assistant for this
    session only (they override ``assistant_settings.json``). ``partner`` and
    ``support_settings`` are the old names of ``opponent`` and
    ``assistant_settings`` and still work (the new names win). ``study``
    (``"project/study"``) runs the session in that study (default: the current one).
    """
    if home is not None or "HANI2_HOME" not in os.environ:
        os.environ["HANI2_HOME"] = home or tempfile.mkdtemp(prefix="hani2-test-")
    os.environ.setdefault("HANI2_EVENTS", "0")
    q = dict(query or {})
    opponent = opponent or partner
    if opponent:
        q.setdefault("opponents", opponent)

    from hani2.support_agent import runtime
    from hani2.support_agent.settings import load_assistant_settings

    settings = load_assistant_settings()
    settings["mode"] = "on"
    if agent_class is not None:
        settings["agent_class"] = agent_class
    settings.update(support_settings or {})
    settings.update(assistant_settings or {})

    original = runtime.load_support_agent_settings
    runtime.load_support_agent_settings = lambda: settings  # type: ignore[assignment]
    old_env = {v: os.environ.pop(v, None) for v in ("HANI2_ASSISTANT", "HANI2_SUPPORT_AGENT")}
    try:
        extra = {"study": study} if study is not None else {}
        s = TestSession(f"test:{uuid.uuid4().hex[:8]}", user, mode=mode, is_admin=is_admin, query=q, hub=_Collector(),
                        **extra)
    finally:
        runtime.load_support_agent_settings = original  # type: ignore[assignment]
        for v, value in old_env.items():
            if value is not None:
                os.environ[v] = value
    s.admin_prefs["n_steps"] = n_steps
    s.admin_prefs["time_limit"] = time_limit
    s.admin_prefs["allow_scenario_selection"] = True
    if load:
        s.load(scenario_type)
    return s
