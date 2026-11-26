"""Human opponents: two participants negotiate with each other.

A project or study chooses its opponents: AI agents (as always), another
participant alone (the reserved opponent entry ``human``) or another
participant with an Assistant (``human+assistant``). For example
``opponents: [human+assistant]`` in study.yaml, ``?opponents=human`` or
``--opponents human,:pan``. When a session's next opponent is one of these, the
session is paired, as it loads its scenario, with another session that is
waiting for a human opponent under the same *match key*, when each side is what
the other asked for (``human``: a side without an Assistant; ``human+assistant``:
a side with one):

- the first session loads its scenario as usual and waits in the lobby;
- the second takes the same scenario and the other side of it;
- the negotiation starts once both have pressed Start (or were started).

Each side keeps its own browser session, tools and Assistant. Team against team:
one study with an Assistant and ``opponents: [human+assistant]``. Human against
human: a study without an Assistant and ``opponents: [human]``. Team against a
human alone: two studies of one project, one with an Assistant and ``opponents:
[human]``, the other without and ``opponents: [human+assistant]``.

The match key is ``?match=<code>`` when the page has one (two people who share
a code meet each other), else the project (so its studies can be paired). One
:class:`Match` owns the shared mechanism and the lock that steps it. A side
only ever steps the mechanism for its own action; the other side is woken
through its own :meth:`~hani2.session.NegotiationSession.submit`.

When nobody joins within ``human_opponent_wait`` seconds (an admin setting,
default 120; 0 waits forever), the waiting side gets an opponent from the rest of
its pool (``human_opponent_fallback``, default on). A side that leaves (its
session is closed) ends a running negotiation: its seat ends the negotiation on
its next turn. A side that leaves before the start puts the other back in the lobby.
"""

from __future__ import annotations

import random
import threading
import traceback
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from hani2.session import NegotiationSession

#: the opponent-pool entries that mean "another participant" (alone / with an Assistant)
HUMAN = "human"
HUMAN_ASSISTED = "human+assistant"
_ASSISTED_SPELLINGS = {"human+assistant", "human_assistant", "human-assistant", "human + assistant"}
DEFAULT_WAIT = 120.0


def _norm(spec: Any) -> str:
    return spec.strip().lower() if isinstance(spec, str) else ""


def is_human(spec: Any) -> bool:
    """Whether an opponent spec is one of the reserved entries ``human`` / ``human+assistant``."""
    n = _norm(spec)
    return n == HUMAN or n in _ASSISTED_SPELLINGS


def wants_assistant(spec: Any) -> bool:
    """Whether a human-opponent spec asks for an opponent with an Assistant."""
    return _norm(spec) in _ASSISTED_SPELLINGS


def canonical(spec: Any) -> str:
    return HUMAN_ASSISTED if wants_assistant(spec) else HUMAN


def match_key(session: "NegotiationSession") -> str:
    """The lobby key of a session: ``?match=<code>`` or its study."""
    q = session.query or {}
    code = q.get("match")
    if isinstance(code, (list, tuple)):
        code = code[0] if code else None
    code = str(code or "").strip()
    if code:
        return f"code:{code}"
    ref = session.study_ref
    return f"project:{ref.project}" if ref is not None else "project:"


def wait_seconds(session: "NegotiationSession") -> float:
    try:
        v = session.admin_prefs.get("human_opponent_wait", DEFAULT_WAIT)
        return float(DEFAULT_WAIT if v is None else v)
    except (TypeError, ValueError):
        return DEFAULT_WAIT


class Match:
    """Two seats (by human index) negotiating one scenario."""

    def __init__(self, key: str, host: "NegotiationSession", host_index: int, scenario: Any, info: dict,
                 sdir: Any, evaluation: Any, want_assistant: bool = False, has_assistant: bool = False):
        self.id = uuid.uuid4().hex[:12]
        self.key = key
        self.scenario = scenario
        self.info = info
        self.sdir = sdir
        self.evaluation = evaluation
        self.host = host
        self.seats: dict[int, "NegotiationSession"] = {host_index: host}
        #: per seat: whether it wants an opponent with an Assistant / has an Assistant itself
        self.wants: dict[int, bool] = {host_index: bool(want_assistant)}
        self.has: dict[int, bool] = {host_index: bool(has_assistant)}
        self.ready: set[int] = set()
        self.left: set[int] = set()
        self.mechanism = None
        self.began = False
        self.lock = threading.RLock()
        #: the one lock that steps the shared mechanism (both seats use it as their step_lock)
        self.step_lock = threading.Lock()
        self._timer: threading.Timer | None = None

    # -- seats -----------------------------------------------------------------
    @property
    def paired(self) -> bool:
        return len(self.seats) == 2

    def index_of(self, s: "NegotiationSession") -> int | None:
        return next((i for i, x in self.seats.items() if x is s), None)

    def other(self, s: "NegotiationSession") -> "NegotiationSession | None":
        i = self.index_of(s)
        return None if i is None else self.seats.get(1 - i)

    def free_index(self) -> int:
        return 1 - next(iter(self.seats))

    def accepts(self, want_assistant: bool, has_assistant: bool) -> bool:
        """Whether a side that wants / has an Assistant fits the waiting seat (and the seat fits it)."""
        i = next(iter(self.seats))
        return self.has[i] == bool(want_assistant) and self.wants[i] == bool(has_assistant)

    def has_left(self, s: "NegotiationSession") -> bool:
        i = self.index_of(s)
        return i is not None and i in self.left

    def seat_ids(self) -> set[str]:
        """The negotiator ids of the seats still present (a seat that left is stepped like an agent)."""
        return {str(x.ss.get("human_id")) for i, x in self.seats.items() if i not in self.left}

    # -- the lobby timer -------------------------------------------------------
    def arm(self, seconds: float) -> None:
        self.cancel_timer()
        if seconds and seconds > 0:
            self._timer = threading.Timer(seconds, self._no_partner)
            self._timer.daemon = True
            self._timer.start()

    def cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _no_partner(self) -> None:
        with self.lock:
            if self.paired or self.began:
                return
            host = self.host
        LOBBY.withdraw(self)
        if host.closed:
            return
        host.submit(host._no_human_opponent, self)

    # -- starting --------------------------------------------------------------
    def seat_ready(self, s: "NegotiationSession") -> bool:
        """Mark ``s`` ready to start; build the mechanism and wake both seats once both are.
        Returns whether the negotiation began now."""
        with self.lock:
            i = self.index_of(s)
            if i is None or self.began:
                return False
            self.ready.add(i)
            if not (self.paired and self.ready >= {0, 1}):
                return False
            self.began = True
            self.cancel_timer()
        try:
            self.mechanism = self.host._make_match_mechanism(self)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            with self.lock:
                self.began = False
                self.ready.clear()
            for x in list(self.seats.values()):
                x.submit(x._match_failed, str(e))
            return False
        for x in list(self.seats.values()):
            x.submit(x._start_running)
        return True

    # -- stepping --------------------------------------------------------------
    def after_step(self, s: "NegotiationSession") -> None:
        """``s`` just acted: wake the other seat (or, when it left, step its seat)."""
        o = self.other(s)
        if o is None:
            return
        if self.has_left(o):
            s.submit(s._step_absent_seat)
        else:
            o.submit(o._match_turn)

    # -- leaving ---------------------------------------------------------------
    def leave(self, s: "NegotiationSession") -> None:
        with self.lock:
            i = self.index_of(s)
            if i is None:
                return
            if not self.began:
                # not started: the other seat (if any) waits for someone else
                del self.seats[i]
                self.wants.pop(i, None)
                self.has.pop(i, None)
                self.ready.discard(i)
                rest = next(iter(self.seats.values()), None)
                if rest is None:
                    self.cancel_timer()
                    LOBBY.withdraw(self)
                    return
                self.host = rest
            else:
                self.left.add(i)
                rest = self.seats.get(1 - i)
        if rest is None or rest.closed:
            return
        # never call into the other session here (the caller may hold its own session's lock)
        if not self.began:
            LOBBY.requeue(self)
            rest.submit(rest._match_partner_left, False)
            return
        rest.submit(rest._match_partner_left, True)


class Lobby:
    """Sessions waiting for a human opponent, by match key (one server process)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.waiting: dict[str, list[Match]] = {}

    def pair(self, s: "NegotiationSession", want_assistant: bool = False, has_assistant: bool = False) -> Match | None:
        """A waiting match ``s`` can join (it is then seated), else ``None``. ``want_assistant``:
        ``s`` asks for an opponent with an Assistant; ``has_assistant``: ``s`` has one."""
        key = match_key(s)
        with self._lock:
            queue = self.waiting.get(key) or []
            for m in list(queue):
                with m.lock:
                    host = m.host
                    if host.closed or host.phase not in ("ready", "starting") or host.match is not m:
                        queue.remove(m)
                        m.cancel_timer()
                        continue
                    if host is s or m.paired or not m.accepts(want_assistant, has_assistant):
                        continue
                    queue.remove(m)
                    m.cancel_timer()
                    i = m.free_index()
                    m.seats[i] = s
                    m.wants[i], m.has[i] = bool(want_assistant), bool(has_assistant)
                    return m
        return None

    def host(self, s: "NegotiationSession", host_index: int, scenario: Any, info: dict, sdir: Any,
             evaluation: Any, want_assistant: bool = False, has_assistant: bool = False) -> Match:
        m = Match(match_key(s), s, host_index, scenario, info, sdir, evaluation, want_assistant, has_assistant)
        s.match = m  # before it is visible to a joining session
        self.requeue(m)
        return m

    def requeue(self, m: Match) -> None:
        with self._lock:
            q = self.waiting.setdefault(m.key, [])
            if m not in q:
                q.append(m)
        m.arm(wait_seconds(m.host))

    def withdraw(self, m: Match) -> None:
        with self._lock:
            q = self.waiting.get(m.key) or []
            if m in q:
                q.remove(m)
            if not q:
                self.waiting.pop(m.key, None)

    def n_waiting(self, key: str | None = None) -> int:
        with self._lock:
            if key is not None:
                return len(self.waiting.get(key) or [])
            return sum(len(q) for q in self.waiting.values())

    def clear(self) -> None:
        with self._lock:
            for q in self.waiting.values():
                for m in q:
                    m.cancel_timer()
            self.waiting.clear()


LOBBY = Lobby()


def fallback_opponent(pool: list) -> Any:
    """An opponent from ``pool`` other than ``human`` (the built-in default pool when none is left)."""
    from hani2.agents import DEFAULT_POOL

    rest = [p for p in pool if not is_human(p)]
    return random.choice(rest or list(DEFAULT_POOL))
