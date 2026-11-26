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
import re
import threading
import time
import traceback
import uuid
import weakref
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from hani2.session import NegotiationSession

#: the opponent-pool entries that mean "another participant" (alone / with an Assistant)
HUMAN = "human"
HUMAN_ASSISTED = "human+assistant"
DEFAULT_WAIT = 120.0
#: seconds a seat may have no open page before it counts as having left
DEFAULT_ABSENT = 60.0
#: how often a match checks for absent seats and partners who never press Start
TICK = 2.0


def _norm(spec: Any) -> str:
    """``human+assistant`` however it is written (``human assistant`` is what ``+`` in a URL decodes to,
    ``human_assistant``, ``Human + Assistant``); other strings lowercased."""
    if not isinstance(spec, str):
        return ""
    return re.sub(r"[\s+_-]+", "+", spec.strip().lower())


def is_human(spec: Any) -> bool:
    """Whether an opponent spec is one of the reserved entries ``human`` / ``human+assistant``."""
    return _norm(spec) in (HUMAN, HUMAN_ASSISTED)


def wants_assistant(spec: Any) -> bool:
    """Whether a human-opponent spec asks for an opponent with an Assistant."""
    return _norm(spec) == HUMAN_ASSISTED


def canonical(spec: Any) -> str:
    return HUMAN_ASSISTED if wants_assistant(spec) else HUMAN


def kinds(want: Any) -> frozenset[bool]:
    """What a side accepts as its opponent, as a set of "has an Assistant" values: ``True`` (a
    ``human+assistant`` side), ``False`` (a ``human`` side) or both (any person)."""
    if isinstance(want, (set, frozenset, list, tuple)):
        return frozenset(bool(x) for x in want)
    return frozenset({bool(want)})


def kinds_of(pool: list) -> frozenset[bool]:
    """The human kinds a pool lists (``human`` → ``False``, ``human+assistant`` → ``True``)."""
    return frozenset(wants_assistant(p) for p in pool if is_human(p))


def codes_allowed(session: NegotiationSession) -> bool:
    """Whether ``?match=<code>`` pairs this session (admins always; others unless the study sets
    ``human_opponent_codes: false``)."""
    if getattr(session, "is_admin", False):
        return True
    v = (getattr(session, "admin_prefs", None) or {}).get("human_opponent_codes", True)
    return not (v is False or str(v).strip().lower() in ("0", "false", "no", "off"))


def match_key(session: NegotiationSession) -> str:
    """The lobby key of a session: ``?match=<code>`` or its study."""
    q = session.query or {}
    code = q.get("match") if codes_allowed(session) else None
    if isinstance(code, (list, tuple)):
        code = code[0] if code else None
    code = str(code or "").strip()
    if code:
        return f"code:{code}"
    ref = session.study_ref
    return f"project:{ref.project}" if ref is not None else "project:"


def _pref(session: NegotiationSession, key: str, default: float) -> float:
    try:
        v = session.admin_prefs.get(key, default)
        return float(default if v is None else v)
    except (TypeError, ValueError):
        return default


def wait_seconds(session: NegotiationSession) -> float:
    return _pref(session, "human_opponent_wait", DEFAULT_WAIT)


def absent_seconds(session: NegotiationSession) -> float:
    return _pref(session, "human_opponent_absent", DEFAULT_ABSENT)


def has_page(session: NegotiationSession) -> bool | None:
    """Whether the session has an open page (``None``: unknown, e.g. a headless session)."""
    hub = getattr(session, "hub", None)
    n = getattr(hub, "n_connections", None)
    if n is None:
        return None
    try:
        return n(session.sid) > 0
    except Exception:  # noqa: BLE001
        return None


class Match:
    """Two seats (by human index) negotiating one scenario."""

    def __init__(self, key: str, host: NegotiationSession, host_index: int, scenario: Any, info: dict,
                 sdir: Any, evaluation: Any, want_assistant: bool = False, has_assistant: bool = False):
        self.id = uuid.uuid4().hex[:12]
        self.key = key
        self.scenario = scenario
        self.info = info
        self.sdir = sdir
        self.evaluation = evaluation
        self.host = host
        self.seats: dict[int, NegotiationSession] = {host_index: host}
        #: per seat: which opponents it accepts (see :func:`kinds`) / whether it has an Assistant itself
        self.wants: dict[int, frozenset[bool]] = {host_index: kinds(want_assistant)}
        self.has: dict[int, bool] = {host_index: bool(has_assistant)}
        self.ready: set[int] = set()
        self.left: set[int] = set()
        self.mechanism = None
        self.began = False
        self.lock = threading.RLock()
        #: the one lock that steps the shared mechanism (only the side whose turn it is steps)
        self.step_lock = threading.Lock()
        self._timer: threading.Timer | None = None
        #: when each seat was first seen without an open page / pressed Start (for the watcher)
        self._absent_since: dict[int, float] = {}
        self._first_ready_at: float | None = None
        self._watching = False
        self._stopped = False

    # -- seats -----------------------------------------------------------------
    @property
    def paired(self) -> bool:
        return len(self.seats) == 2

    def index_of(self, s: NegotiationSession) -> int | None:
        return next((i for i, x in self.seats.items() if x is s), None)

    def other(self, s: NegotiationSession) -> NegotiationSession | None:
        i = self.index_of(s)
        return None if i is None else self.seats.get(1 - i)

    def free_index(self) -> int:
        return 1 - next(iter(self.seats))

    def accepts(self, want_assistant: Any, has_assistant: bool) -> bool:
        """Whether a side that accepts ``want_assistant`` (see :func:`kinds`) and has / has not an
        Assistant fits the waiting seat, and the seat fits it."""
        i = next(iter(self.seats))
        return self.has[i] in kinds(want_assistant) and bool(has_assistant) in self.wants[i]

    def has_left(self, s: NegotiationSession) -> bool:
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
    def seat_ready(self, s: NegotiationSession) -> bool:
        """Mark ``s`` ready to start; build the mechanism and wake both seats once both are.
        Returns whether the negotiation began now."""
        with self.lock:
            i = self.index_of(s)
            if i is None or self.began:
                return False
            self.ready.add(i)
            if self._first_ready_at is None and self.paired:
                self._first_ready_at = time.time()
            if not (self.paired and self.ready >= {0, 1}):
                self.watch()
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
        self.watch()
        return True

    # -- the watcher: partners who never press Start, pages closed for good ------
    def finished(self) -> bool:
        if not self.seats:
            return True
        m = self.mechanism
        return self.began and (m is None or m.state.done or len(self.left) == 2)

    def watch(self) -> None:
        """Check the seats every :data:`TICK` seconds until the match is over (idempotent)."""
        with self.lock:
            if self._watching:
                return
            self._watching = True
        self._schedule_tick()

    def _schedule_tick(self) -> None:
        t = threading.Timer(TICK, self._tick)
        t.daemon = True
        t.start()

    def _tick(self) -> None:
        try:
            if self._check():
                self._schedule_tick()
                return
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._schedule_tick()
            return
        with self.lock:
            self._watching = False

    def _check(self) -> bool:
        """One look at the seats; returns whether to keep watching."""
        if self.finished() or self._stopped:
            return False
        if not self.began and all(s.match is not self or s.closed for s in list(self.seats.values())):
            return False  # everyone moved on (an AI opponent after the wait, a new round)
        now = time.time()
        gone: list[NegotiationSession] = []
        with self.lock:
            for i, s in list(self.seats.items()):
                if i in self.left:
                    continue
                page = has_page(s)
                if page is False and not s.closed:
                    self._absent_since.setdefault(i, now)
                    if now - self._absent_since[i] >= absent_seconds(s):
                        gone.append(s)
                else:
                    self._absent_since.pop(i, None)
            stalled = None
            if not self.began and self.paired and self.ready and self._first_ready_at is not None:
                waiting_on = [s for i, s in self.seats.items() if i not in self.ready]
                limit = wait_seconds(self.host)
                if waiting_on and limit > 0 and now - self._first_ready_at >= limit:
                    stalled = waiting_on[0]
        if not self.began and not self.paired:
            # a waiting host whose page is gone: nobody should be paired with them (the fallback
            # timer still runs, so they get an AI opponent if they come back)
            if gone:
                LOBBY.withdraw(self)
                return False
            return True
        for s in gone:
            self.abandon(s)
        if stalled is not None and stalled not in gone:
            self.abandon(stalled)
        return not self.finished() and (self.began or self.paired)

    def abandon(self, s: NegotiationSession) -> None:
        """``s`` is treated as having left (its page has been closed too long, or it never
        pressed Start) without closing its session."""
        with self.lock:
            i = self.index_of(s)
            if i is None or i in self.left:
                return
            began = self.began
        if began:
            with self.lock:
                self.left.add(i)
            s.ss["match_abandoned"] = "self"
            o = self.other(s)
            if o is not None:
                o.ss["match_abandoned"] = "opponent"
                o.submit(o._match_partner_left, True)
            return
        # not started: free the seat; the one left waits for someone else, and the one who
        # stalled gets a match of their own for the scenario they hold
        with self.lock:
            want, has = self.wants.get(i, kinds(False)), self.has.get(i, False)
            o = self.seats.get(1 - i)
        if o is not None:
            s.__dict__.setdefault("_avoid_sids", set()).add(o.sid)
            o.__dict__.setdefault("_avoid_sids", set()).add(s.sid)
        self.leave(s)
        s.submit(s._match_kicked, self, i, want, has)

    # -- stepping --------------------------------------------------------------
    def after_step(self, s: NegotiationSession) -> None:
        """``s`` just acted: wake the other seat (or, when it left, step its seat)."""
        o = self.other(s)
        if o is None:
            return
        if self.has_left(o):
            s.submit(s._step_absent_seat)
        else:
            o.submit(o._match_turn)

    # -- leaving ---------------------------------------------------------------
    def leave(self, s: NegotiationSession) -> None:
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
                self._absent_since.clear()
                self._first_ready_at = None  # unpaired again
                rest = next(iter(self.seats.values()), None)
                if rest is None:
                    self.cancel_timer()
                else:
                    self.host = rest
            else:
                self.left.add(i)
                rest = self.seats.get(1 - i)
                s.ss["match_abandoned"] = "self"
                if rest is not None:
                    rest.ss["match_abandoned"] = "opponent"
        if rest is None and not self.began:
            LOBBY.withdraw(self)  # outside self.lock: the lobby takes its lock first, then a match's
            return
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
        self._loading: dict[str, threading.Lock] = {}
        #: sessions showing the "play a person / an AI" choice, by match key (told when the lobby changes)
        self._watchers: dict[str, "weakref.WeakSet[NegotiationSession]"] = {}

    def loading(self, s: NegotiationSession) -> threading.Lock:
        """The lock a session holds from looking for a partner until it waits in the lobby."""
        key = match_key(s)
        with self._lock:
            return self._loading.setdefault(key, threading.Lock())

    def _fits(self, m: Match, s: NegotiationSession, want: Any, has: bool, queue: list) -> bool:
        """Whether waiting ``m`` fits ``s`` (drops matches whose host is gone); call with the lock held."""
        with m.lock:
            host = m.host
            # a host may be answering the pre-questionnaire / consent form of its first round
            if host.closed or host.phase not in ("ready", "starting", "questionnaire") or host.match is not m:
                if m in queue:
                    queue.remove(m)
                m.cancel_timer()
                return False
            if host is s or m.paired or not m.accepts(want, has):
                return False
            if host.sid in getattr(s, "_avoid_sids", ()) or s.sid in getattr(host, "_avoid_sids", ()):
                return False  # these two were just separated (one did not press Start)
            return True

    def pair(self, s: NegotiationSession, want_assistant: Any = False, has_assistant: bool = False) -> Match | None:
        """A waiting match ``s`` can join (it is then seated), else ``None``: one at random among those
        that fit. ``want_assistant``: the opponents ``s`` accepts (see :func:`kinds`); ``has_assistant``:
        whether ``s`` has an Assistant."""
        key = match_key(s)
        with self._lock:
            queue = self.waiting.get(key) or []
            fits = [m for m in list(queue) if self._fits(m, s, want_assistant, has_assistant, queue)]
            if not fits:
                return None
            m = random.choice(fits)  # random among the people waiting: nobody can aim at someone
            with m.lock:
                queue.remove(m)
                m.cancel_timer()
                i = m.free_index()
                m.seats[i] = s
                m.wants[i], m.has[i] = kinds(want_assistant), bool(has_assistant)
                if m.ready:  # the waiting side already pressed Start: the clock for the other starts now
                    m._first_ready_at = time.time()
            m.watch()  # from now on: partners who never press Start, pages closed for good
        self.notify(key)
        return m

    def n_fitting(self, s: NegotiationSession, want_assistant: Any, has_assistant: bool) -> int:
        """How many people waiting now ``s`` could be paired with."""
        key = match_key(s)
        with self._lock:
            queue = self.waiting.get(key) or []
            return sum(1 for m in list(queue) if self._fits(m, s, want_assistant, has_assistant, queue))

    def watch_choice(self, s: NegotiationSession, on: bool = True) -> None:
        """``s`` shows the choice between a person and an AI: push its state when the lobby changes."""
        key = match_key(s)
        with self._lock:
            ws = self._watchers.setdefault(key, weakref.WeakSet())
            if on:
                ws.add(s)
            else:
                ws.discard(s)

    def notify(self, key: str) -> None:
        with self._lock:
            ws = list(self._watchers.get(key) or ())
        for w in ws:
            if not w.closed:
                try:
                    w.push_state()
                except Exception:  # noqa: BLE001
                    traceback.print_exc()

    def host(self, s: NegotiationSession, host_index: int, scenario: Any, info: dict, sdir: Any,
             evaluation: Any, want_assistant: Any = False, has_assistant: bool = False) -> Match:
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
        m.watch()
        self.notify(m.key)

    def withdraw(self, m: Match) -> None:
        with self._lock:
            q = self.waiting.get(m.key) or []
            if m in q:
                q.remove(m)
            if not q:
                self.waiting.pop(m.key, None)
        self.notify(m.key)

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
                    m._stopped = True
            self.waiting.clear()
            self._watchers.clear()


LOBBY = Lobby()


def fallback_opponent(pool: list) -> Any:
    """An opponent from ``pool`` other than ``human`` (the built-in default pool when none is left)."""
    from hani2.agents import DEFAULT_POOL

    rest = [p for p in pool if not is_human(p)]
    return random.choice(rest or list(DEFAULT_POOL))
