"""Assigning Assistants, opponents and scenarios to the humans of a study.

* **Assistant pool.** Where a session's Assistant pool comes from, first hit wins:

  1. ``?assistant=`` / ``?assistants=`` in the page URL (admins only), else the
     ``assistant`` key (old name ``support_agent``) of the opponent group file the
     participant arrived with (``?group=<key>``);
  2. ``schedule.json`` (written by an outside system): the slot's ``assistant``,
     else the top-level ``assistant``;
  3. ``HANI2_ASSISTANTS`` (``hani2 --assistants``), else ``HANI2_ASSISTANT_CLASS``
     (``hani2 --assistant <class>``);
  4. ``assistants`` in study.yaml, else in project.yaml;
  5. ``agent_class`` in assistant_settings.json (the single configured class).

  At every level an Assistant that cannot be imported or created leaves the session
  without an Assistant and shows the error (a banner, a toast, an ``ERROR`` event,
  the ``assistant_error`` column); there is no silent fallback to the built-in one.

* **No Assistant (a control arm).** The pool member ``none`` is a level like any
  other: humans assigned to it negotiate without an Assistant (no panel, no
  Assistant-driven autopilot, no Assistant questions) and their rows say
  ``assistant = none``. ``assistants: [MyAssistant, none]`` with ``balanced``
  scheduling splits a study into an Assistant group and a no-Assistant control
  group on the same scenarios and opponents.

* **Scheduling.** Who gets which pool member is the study's ``assistants``
  scheduling method (:mod:`hani2.scheduling`; default ``balanced``):

  - ``balanced``: each human keeps one Assistant for every negotiation in the
    study; a new human gets the pool member with the fewest humans assigned so far
    in that study, ties going to the earlier member in pool order;
  - ``random_fixed``: kept per human, drawn at random on arrival;
  - ``round_robin``: kept per human, member ``index mod size``;
  - ``random_each``: drawn again for every negotiation (not recorded as fixed);
  - ``external``: only ``schedule.json`` names the Assistant (else an error).

  This holds for pools from a group file (with more than one Assistant),
  ``--assistants``, study.yaml / project.yaml and the settings; an admin's
  ``?assistant=``, a schedule.json entry and a group file naming one Assistant are
  used as given (the first member) and not recorded. Admins and playground guests
  (``guest_*``) get an Assistant the same way but are neither recorded nor counted.
  A human counts once assigned, even if they drop out. If a human's Assistant
  leaves the pool they are assigned again (the old one is kept under
  ``previous_assistants`` and no longer counted).

* **Participant index.** Every counted human of a study gets the next index (0, 1,
  …) on first sight; it picks their row of the opponent Latin square and their
  scenario type.

Everything is kept in ``<study results>/assignments.json``, read and written under
a thread lock and a file lock, written atomically.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from hani2 import groups, projects

if TYPE_CHECKING:  # pragma: no cover
    from hani2.session import NegotiationSession

FILE = "assignments.json"
ASSISTANTS_ENV = "HANI2_ASSISTANTS"

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_LOCK = threading.Lock()


# --------------------------------------------------------------------------- #
# The assignments file                                                         #
# --------------------------------------------------------------------------- #
def store_path(ref: Any = projects.UNSET) -> Path:
    """``assignments.json`` of study ``ref`` (default: the current study)."""
    from hani2.config import results_root

    r = projects.current_study() if ref is projects.UNSET else ref
    with projects.use_study(r):
        return results_root() / FILE


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    key = str(path.resolve())
    with _LOCKS_LOCK:
        lock = _LOCKS.setdefault(key, threading.Lock())
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(path.with_name(path.name + ".lock"), "a+")
        try:
            try:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except (ImportError, OSError):  # pragma: no cover - no file locks here
                pass
            yield
        finally:
            fh.close()  # releases the file lock


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            data.setdefault("humans", {})
            return data
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        print(f"[hani2] {path} is broken ({e}); starting a new one next to it")
        try:
            path.replace(path.with_name(path.name + f".broken-{int(datetime.now().timestamp())}"))
        except OSError:
            pass
    return {"version": 1, "humans": {}, "next_index": 0}


def _write(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def read_assignments(ref: Any = projects.UNSET) -> dict[str, Any]:
    path = store_path(ref)
    with _locked(path):
        return _read(path)


def counts_as_human(session: "NegotiationSession") -> bool:
    """Whether a session's human is recorded and counted for balancing (not admins, admins in participant
    view, playground guests or simulated participants)."""
    return (not session.is_admin and not getattr(session, "admin_viewer", None)
            and not getattr(session, "uncounted", False)  # e.g. the No-Human ablation runs
            and not str(session.user).startswith(("guest_", "sim_"))
            and not str(getattr(session, "sid", "")).startswith("play:")  # a signed-in user's playground
            and getattr(session, "mode", "") != "simulated")


def _human(data: dict, user: str) -> dict[str, Any]:
    h = data["humans"].get(user)
    if h is None:
        idx = int(data.get("next_index", len(data["humans"])))
        h = {"index": idx, "first_seen": datetime.now().isoformat()}
        data["humans"][user] = h
        data["next_index"] = idx + 1
    return h


def participant_index(session: "NegotiationSession") -> int | None:
    """The human's index within the study (assigned on first call); ``None`` for admins and guests."""
    if not counts_as_human(session):
        return None
    path = store_path(session.study_ref)
    with _locked(path):
        data = _read(path)
        known = session.user in data["humans"]
        h = _human(data, session.user)
        if not known:
            _write(path, data)
        return int(h["index"])


def assistant_counts(data: dict[str, Any], pool: list[str]) -> dict[str, int]:
    counts = {p: 0 for p in pool}
    for h in data.get("humans", {}).values():
        a = h.get("assistant")
        if a in counts:
            counts[a] += 1
    return counts


def _least(pool: list[str], counts: dict[str, int]) -> str:
    return min(pool, key=lambda p: (counts.get(p, 0), pool.index(p)))


def _seed(session: Any) -> str:
    return f"{session.study_ref or ''}|{session.user}"


def assign_assistant(session: "NegotiationSession", pool: list[str], group: str | None = None,
                     method: str = "balanced") -> str:
    """The human's Assistant from ``pool``, kept per human (``method``: ``balanced``,
    ``random_fixed`` or ``round_robin``; see the module docs)."""
    from hani2 import scheduling

    if not pool:
        raise ValueError("empty Assistant pool")
    path = store_path(session.study_ref)
    if not counts_as_human(session):
        prev = getattr(session, "_uncounted_assistant", None)
        if prev in pool:
            return prev
        if len(pool) == 1:
            choice = pool[0]
        elif method == "random_fixed":
            choice = scheduling.pick_assistant_fixed(method, pool, 0, {}, _seed(session))
        else:
            with _locked(path):
                choice = _least(pool, assistant_counts(_read(path), pool))
        session._uncounted_assistant = choice  # type: ignore[attr-defined]
        return choice
    with _locked(path):
        data = _read(path)
        h = _human(data, session.user)
        if h.get("assistant") in pool:
            choice = h["assistant"]
            if h.get("assistant_group") != group and group:
                h["assistant_group"] = group
                _write(path, data)
            return choice
        if h.get("assistant"):
            h.setdefault("previous_assistants", []).append(h["assistant"])
        seed = _seed(session) + (f"|{len(h['previous_assistants'])}" if h.get("previous_assistants") else "")
        choice = scheduling.pick_assistant_fixed(method, pool, int(h["index"]), assistant_counts(data, pool), seed)
        h.update(assistant=choice, assistant_group=group or "", assistant_scheduling=method,
                 assigned_at=datetime.now().isoformat())
        _write(path, data)
        return choice


# --------------------------------------------------------------------------- #
# Latin squares                                                                #
# --------------------------------------------------------------------------- #
def latin_square(n: int) -> list[list[int]]:
    """A balanced Latin square (Williams design) over ``n`` items: every item
    appears once per row and once per position, and every item follows every
    other item equally often. ``n`` rows for even ``n``; ``2n`` rows (each row and
    its reverse) for odd ``n``."""
    if n <= 0:
        return []
    if n == 1:
        return [[0]]
    first, lo, hi = [0], 1, n - 1
    while len(first) < n:
        first.append(lo)
        lo += 1
        if len(first) < n:
            first.append(hi)
            hi -= 1
    rows = [[(x + r) % n for x in first] for r in range(n)]
    if n % 2:
        rows += [list(reversed(row)) for row in rows]
    return rows


def latin_pick(pool: list, index: int, slot: int) -> Any:
    """The item of ``pool`` for participant ``index`` in slot ``slot``."""
    rows = latin_square(len(pool))
    row = rows[index % len(rows)]
    return pool[row[slot % len(row)]]


# --------------------------------------------------------------------------- #
# Which Assistant a session gets                                               #
# --------------------------------------------------------------------------- #
#: the Assistant pool member that means "no Assistant" (the no-Assistant control arm)
NO_ASSISTANT = "none"


def is_no_assistant(spec: Any) -> bool:
    """Whether ``spec`` is the no-Assistant pool member (``none``, any case)."""
    return isinstance(spec, str) and spec.strip().lower() == NO_ASSISTANT


@dataclass
class AssistantChoice:
    spec: str | None
    group: str = ""
    #: query | group | schedule | env | study | settings
    source: str = "settings"
    pool: list[str] = field(default_factory=list)
    error: str | None = None
    #: the scheduling method that picked ``spec`` ("external" for schedule.json, "" for an explicit choice)
    scheduling: str = ""

    @property
    def strict(self) -> bool:
        """Every Assistant fails loudly (kept for callers of the old API; always ``True``)."""
        return True

    def to_dict(self) -> dict[str, Any]:
        return dict(assistant=self.spec or "", assistant_group=self.group, assistant_source=self.source,
                    assistant_pool=list(self.pool), assistant_error=self.error or "",
                    assistant_scheduling=self.scheduling)


def _query_val(query: dict, *names: str) -> str:
    for n in names:
        v = query.get(n)
        if isinstance(v, (list, tuple)):
            v = v[0] if v else None
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _items(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(",") if s.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(s).strip() for s in raw if str(s).strip()]
    return [str(raw).strip()]


def _group_of(items: list[str]) -> str:
    """The group name when a level names exactly one group token."""
    if len(items) == 1 and items[0].startswith((":", "@")):
        return items[0][1:]
    return ""


def _negotiations_done(session: Any) -> int:
    """How many negotiations the human has finished (their results rows): the same number in a
    reconnect, a new session or a later visit, until the next negotiation ends."""
    ss = getattr(session, "ss", None) or {}
    path = ss.get("user_path")
    try:
        import csv

        with open(Path(path) / "results.csv", newline="") as fh:
            return max(0, sum(1 for _ in csv.reader(fh)) - 1)
    except (OSError, TypeError):
        return int(getattr(session, "round_number", 0) or 0)


def _missing() -> str:
    from hani2.scheduling import MISSING_SUFFIX

    return MISSING_SUFFIX


def _assistant_method(session: Any) -> str:
    """The study's ``assistants`` scheduling method (``balanced`` outside a study)."""
    from hani2 import scheduling

    ref = getattr(session, "study_ref", None)
    return scheduling.methods_for(ref)["assistants"] if ref is not None else scheduling.DEFAULTS["assistants"]


def assistant_pool(session: "NegotiationSession", settings: dict, plan: dict | None = None) -> AssistantChoice:
    """The Assistant pool of a session (without picking a member); see the module docs."""
    fixed = getattr(session, "fixed_assistant", None)
    if fixed:  # a session made to run one Assistant (the No-Human ablation runs)
        return AssistantChoice(spec=None, source="fixed", pool=[str(fixed)])
    ref = session.study_ref
    levels: list[tuple[str, list[str], str]] = []  # (source, items, group)
    q = session.query or {}
    if session.is_admin:
        items = _items(_query_val(q, "assistants", "assistant"))
        if items:
            levels.append(("query", items, _group_of(items)))
    gkey = _query_val(q, "group")
    if gkey and not levels:
        g = groups.find_file(groups.OPPONENT, gkey, ref)
        if g is not None and g.error:
            return AssistantChoice(spec=None, group=gkey.lstrip(":"), source="group", error=g.error)
        if g is not None and g.assistant:
            levels.append(("group", _items(g.assistant), gkey.lstrip(":")))
    if not levels:
        sched = (plan or {}).get("assistant")
        if sched is None:
            fn = getattr(getattr(session, "study", None), "schedule_assistant", None)
            sched = fn() if callable(fn) else None
        if sched:
            items = _items(sched)
            levels.append(("schedule", items, _group_of(items)))
    if not levels and _assistant_method(session) == "external":
        st = getattr(session, "study", None)
        if callable(getattr(st, "is_practice_next", None)) and st.is_practice_next():
            # a practice round: the Assistant of the first counted negotiation
            first = st.schedule_assistant(0, False)
            if first:
                items = _items(first)
                levels.append(("schedule", items, _group_of(items)))
    if not levels and _assistant_method(session) == "external":
        return AssistantChoice(spec=None, source="schedule", scheduling="external" + _missing(),
                               error="the study's Assistant scheduling is 'external' but no schedule.json "
                                     "names an Assistant for this negotiation")
    if not levels:
        raw = (os.environ.get(ASSISTANTS_ENV) or "").strip()
        if not raw:
            from hani2.support_agent.settings import ASSISTANT_CLASS_ENV_VAR, SUPPORT_AGENT_CLASS_ENV_VAR, assistant_env

            raw = (assistant_env(ASSISTANT_CLASS_ENV_VAR, SUPPORT_AGENT_CLASS_ENV_VAR) or "").strip()
        if raw:
            items = _items(raw)
            levels.append(("env", items, _group_of(items)))
    if not levels:
        raw = projects.setting("assistants", None, ref=ref)
        items = _items(raw)
        if items:
            levels.append(("study", items, _group_of(items)))
    if not levels:
        spec = groups.default_assistant_spec(settings)
        return AssistantChoice(spec=None, source="settings", pool=[spec])
    source, items, group = levels[0]
    problems: list[str] = []
    pool = groups.expand_assistants(items, ref, errors=problems)
    if not pool:
        return AssistantChoice(spec=None, group=group, source=source, pool=[],
                               error=f"{', '.join(items)} names no Assistant ({source})"
                                     + (f": {'; '.join(problems)}" if problems else ""))
    return AssistantChoice(spec=None, group=group, source=source, pool=pool)


def choose_assistant(session: "NegotiationSession", settings: dict, plan: dict | None = None) -> AssistantChoice:
    """The Assistant this session should run now (pool + fixed, balanced pick)."""
    from hani2 import scheduling

    c = assistant_pool(session, settings, plan)
    if c.error or not c.pool:
        return c
    if c.source in ("query", "schedule", "fixed") or (c.source == "group" and len(c.pool) == 1):
        # an explicit choice (an admin's URL, the outside system's schedule, a test link's group
        # file naming one Assistant): used as given, not recorded
        c.spec = c.pool[0]
        c.scheduling = "external" if c.source == "schedule" else ""
        return c
    method = _assistant_method(session)
    c.scheduling = method
    if method == "random_each":
        slot = _negotiations_done(session)
        c.spec = c.pool[0] if len(c.pool) == 1 else scheduling.pick_assistant_each(c.pool, slot, _seed(session))
        return c
    c.spec = assign_assistant(session, c.pool, c.group, method)
    return c
