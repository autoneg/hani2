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
  - ``latin_square`` / ``cyclic``: one Assistant per counted negotiation, counterbalanced over
    participants (balanced Williams square / cyclic rotation; not recorded as fixed);
  - ``balanced_subset`` / ``random_subset``: K different Assistants of the N per human (K is
    ``n_required``), planned on arrival and kept as ``assistant_plan`` (with the ``opponent_plan``
    it was balanced against);
  - ``external``: only ``schedule.json`` names the Assistant (else an error).

  In a Paired study the method gives each human a *set* of remaining Assistants
  (:func:`remaining_assistants`) and the pairing picks one of them per match (see
  :mod:`hani2.pairing`).

  This holds for pools from a group file (with more than one Assistant),
  ``--assistants``, study.yaml / project.yaml and the settings; an admin's
  ``?assistant=``, a schedule.json entry and a group file naming one Assistant are
  used as given (the first member) and not recorded. Admins and playground guests
  (``guest_*``) get an Assistant the same way but are neither recorded nor counted.
  A human counts once assigned, even if they drop out. If a human's Assistant
  leaves the pool they are assigned again (the old one is kept under
  ``previous_assistants`` and no longer counted).

  The per-negotiation methods that promise each Assistant at most once per human
  (``latin_square``, ``cyclic``, ``balanced_subset``, ``random_subset``) keep that
  promise when the pool changes during the study: the slots the human already
  played stay, and each open slot gets its planned Assistant while it is still in
  the pool and unused, else the next unused one (:func:`played_assistants`: the
  ``used_assistants`` and the ``assistant`` of their counted results rows). When
  no unused Assistant is left, ``scheduling.assistant_repeats: true`` wraps around;
  otherwise the human finishes early (a ``finished_early`` event and a log line).
  Only a pool that lost a member of the one the human started with
  (``assistant_pool``, recorded on first sight) ends their study early; otherwise
  (a study whose pool was always smaller than K) it warns and wraps, as before.

* **Participant index.** Every counted human of a study gets the next index (0, 1,
  …) on first sight; it picks their row of the opponent Latin square and their
  scenario type. Their crossing rule (``cross``: ``shift`` or ``none``, see
  :func:`cross_rule`) is stored at the same moment and never changes for them.

* **Paired studies.** ``humans[u].used_assistants`` lists ``[assistant, match_id]`` for every
  negotiation the human started (an Assistant is *used* once both sides pressed Start, even if
  the match is abandoned later), ``humans[u].skipped_assistants`` the ones skipped because nobody
  could be paired with them (``pairing.fallback: end``). The match cells live in
  ``<study results>/match_cells.json`` (completed and in-flight matches per cell, and the
  Assistant × position counts), under the same locks.

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
        data = json.loads(path.read_text(encoding="utf-8"))
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
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
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


def _explicit_cross(ref: Any) -> str | None:
    """``scheduling.cross`` as the study's files set it (``None``: unset)."""
    from hani2 import scheduling

    if ref is None:
        return None
    try:
        return scheduling.options_for(ref).get("cross")
    except Exception:  # noqa: BLE001
        return None


def _new_cross(data: dict, explicit: str | None) -> str:
    """The crossing rule of a human seen for the first time: the files' ``cross``, else ``shift`` --
    unless the study already has humans from before crossing existed (no ``cross`` stored), which
    keeps the whole study on ``none``."""
    from hani2 import scheduling

    if explicit:
        return explicit
    if any("cross" not in h for h in data.get("humans", {}).values()):
        return "none"
    return scheduling.CROSS_DEFAULT


def _human(data: dict, user: str, cross: str | None = None) -> dict[str, Any]:
    """The record of ``user`` (created on first sight with the next index and the crossing rule
    ``cross``, the files' ``scheduling.cross``; see :func:`_new_cross`)."""
    h = data["humans"].get(user)
    if h is None:
        idx = int(data.get("next_index", len(data["humans"])))
        rule = _new_cross(data, cross)
        h = {"index": idx, "first_seen": datetime.now().isoformat(), "cross": rule}
        data["humans"][user] = h
        data["next_index"] = idx + 1
    return h


def participant_record(session: "NegotiationSession") -> dict[str, Any] | None:
    """A copy of the human's record in the study (created on first call: index, crossing rule);
    ``None`` for admins and guests."""
    if not counts_as_human(session):
        return None
    cross = _explicit_cross(session.study_ref)
    path = store_path(session.study_ref)
    with _locked(path):
        data = _read(path)
        known = session.user in data["humans"]
        h = _human(data, session.user, cross)
        if not known:
            _write(path, data)
        return dict(h)


def participant_index(session: "NegotiationSession") -> int | None:
    """The human's index within the study (assigned on first call); ``None`` for admins and guests."""
    h = participant_record(session)
    return None if h is None else int(h["index"])


def cross_rule(session: Any) -> str:
    """The crossing rule (``shift`` / ``none``) of the session's human: stored at first sight, so a
    running study never changes it for people already in it (a record from before crossing
    existed means ``none``). Admins and guests use the study's current rule."""
    from hani2 import scheduling

    if getattr(session, "study_ref", None) is None:
        return "none"
    h = participant_record(session) if counts_as_human(session) else None
    if h is None:
        return _explicit_cross(session.study_ref) or scheduling.CROSS_DEFAULT
    return str(h.get("cross") or "none")


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
    cross = _explicit_cross(session.study_ref)
    with _locked(path):
        data = _read(path)
        h = _human(data, session.user, cross)
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


def _plan_size(session: Any) -> int:
    """K: the counted negotiations per human (``n_required``)."""
    k = getattr(getattr(session, "study", None), "n_required", None)
    if isinstance(k, int) and k > 0:
        return k
    return max(1, int(projects.setting("n_required", 5, env="PROLIFIC_N_REQUIRED", cast=int,
                                       ref=getattr(session, "study_ref", None)) or 5))


def _planned_opponents(session: Any, k: int) -> list[Any] | None:
    """The human's own opponent sequence for slots ``0..k-1`` (``None``: not planned by HANI2)."""
    fn = getattr(getattr(session, "study", None), "planned_opponents", None)
    if not callable(fn):
        return None
    try:
        return fn(k)
    except Exception:  # noqa: BLE001
        return None


def _plan_ok(plan: Any, pool: list[str], k: int, method: str, h: dict,
             taken: set[str] = frozenset(), skipped: set[str] = frozenset()) -> bool:
    """Whether a stored plan still holds: its Assistants are in the pool or were already used by
    the human (an Assistant that left the pool after they used it changes nothing), none twice,
    and it covers K or every Assistant left to them."""
    if not (isinstance(plan, list) and len(set(plan)) == len(plan) and h.get("assistant_plan_method") == method):
        return False
    if not all(a in pool or a in taken for a in plan):
        return False
    return len(plan) == min(k, len((set(pool) - set(skipped)) | set(plan)))


def counted_rows(session: Any) -> list[dict]:
    """The human's results rows that count as negotiation slots, in order: a study's counted rows
    (no practice, no empty negotiation) when it counts them, else every row."""
    st = getattr(session, "study", None)
    fn = getattr(st, "counted_rows", None)
    if callable(fn):
        try:
            return list(fn())
        except Exception:  # noqa: BLE001
            return []
    path = (getattr(session, "ss", None) or {}).get("user_path")
    try:
        import csv

        with open(Path(path) / "results.csv", newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except (OSError, TypeError):
        return []


def played_assistants(session: Any) -> list[str]:
    """The Assistants the human has already used in this study, in order: the ones recorded at
    the start of a Paired negotiation (``used_assistants``), then the ``assistant`` of their
    counted results rows. An Assistant here is never planned for them again unless the study
    allows repeats."""
    out = list(used_assistants(session))
    for r in counted_rows(session):
        a = str(r.get("assistant") or "")
        if a and a not in out:
            out.append(a)
    return out


def pool_at_start(session: Any, pool: list[str]) -> list[str]:
    """The Assistant pool the human was first planned against (``assistant_pool`` in
    ``assignments.json``, kept from their first negotiation). It tells a pool that shrank during
    the study (the human finishes early when nothing unused is left) from a study whose pool was
    always smaller than K (it warns and wraps around)."""
    if not counts_as_human(session):
        return list(pool)
    path = store_path(session.study_ref)
    with _locked(path):
        data = _read(path)
        h = data["humans"].get(session.user)
        if isinstance(h, dict) and isinstance(h.get("assistant_pool"), list):
            return list(h["assistant_pool"])
        h = _human(data, session.user, _explicit_cross(session.study_ref))
        h["assistant_pool"] = list(pool)
        _write(path, data)
        return list(pool)


def assistants_wrap(session: Any, method: str, pool: list[str], paired: bool = False) -> bool:
    """Whether a human who has used every Assistant left in ``pool`` gets one again (the plan
    wraps around) instead of finishing early: ``scheduling.assistant_repeats: true``; or, without
    it, when no Assistant of the pool the human started with has left it (a running study whose
    file breaks the rule, a study without a count of negotiations, an admin: warned and wrapped as
    before). Only a pool that lost a member makes the human finish early. In Paired, only a
    one-Assistant pool wraps without ``assistant_repeats``."""
    from hani2 import scheduling

    ref = getattr(session, "study_ref", None)
    options = scheduling.options_for(ref) if ref is not None else {}
    if scheduling.repeats_allowed(method, options):
        return True
    first = set(pool_at_start(session, pool))
    if paired:
        return len(first) <= 1
    return not (first - set(pool))


def _planned_sequence(session: Any, pool: list[str], method: str, k: int) -> list[str]:
    """The human's planned Assistants for slots ``0..k-1`` (a subset plan has at most N)."""
    from hani2 import scheduling

    if method in scheduling.SUBSET_ASSISTANTS:
        return subset_plan(session, pool, method)
    if len(pool) == 1:
        return [pool[0]] * k
    idx = participant_index(session) or 0
    return [scheduling.pick_assistant_slot(method, pool, idx, j, _seed(session)) for j in range(k)]


def subset_plan(session: Any, pool: list[str], method: str) -> list[str]:
    """The human's planned Assistants for ``balanced_subset`` / ``random_subset`` (K of the pool, in
    order), kept in ``assignments.json`` as ``assistant_plan`` (with ``opponent_plan``, the opponent
    sequence it was planned against). Planned on first need; planned again (the old plan kept
    under ``previous_assistant_plans``) when a member the human has not used yet left the pool, or
    K changed. A new plan keeps the Assistants the human already used (:func:`played_assistants`)
    and fills only the open slots, from Assistants they have not used; it is shorter than K when
    too few are left. Admins and guests get a plan that is not recorded."""
    from hani2 import scheduling

    k = _plan_size(session)
    seed = _seed(session)
    opponents = _planned_opponents(session, min(k, len(pool))) if method == "balanced_subset" else None
    played = played_assistants(session)
    skipped = set(skipped_assistants(session))
    taken = set(played) | skipped

    def plan_from(data: dict, user: str | None) -> list[str]:
        if method == "random_subset":
            fresh = scheduling.random_subset(pool, k, seed)
        else:
            others = [(h["assistant_plan"], h.get("opponent_plan")) for u, h in data.get("humans", {}).items()
                      if u != user and isinstance(h.get("assistant_plan"), list)]
            fresh = scheduling.balanced_subset(pool, k, [o[0] for o in others], seed, opponents=opponents,
                                               opponent_plans=[o[1] for o in others])
        if not taken:
            return fresh
        # a re-plan: the slots already played stay, the open ones get Assistants not used yet
        kept = played[:k]
        return kept + scheduling.fill_open_slots(fresh, taken, pool, k, start=len(kept))

    path = store_path(session.study_ref)
    if not counts_as_human(session):
        prev = (getattr(session, "__dict__", None) or {}).get("_uncounted_plan")
        if prev and prev[0] == method and _plan_ok(prev[1], pool, k, method, {"assistant_plan_method": method},
                                                   taken, skipped):
            return list(prev[1])
        with _locked(path):
            plan = plan_from(_read(path), None)
        try:
            session._uncounted_plan = (method, plan)
        except AttributeError:  # pragma: no cover
            pass
        return plan
    cross = _explicit_cross(session.study_ref)
    with _locked(path):
        data = _read(path)
        h = _human(data, session.user, cross)
        plan = h.get("assistant_plan")
        if _plan_ok(plan, pool, k, method, h, taken, skipped):
            return list(plan)
        if plan:
            h.setdefault("previous_assistant_plans", []).append(plan)
        plan = plan_from(data, session.user)
        h.update(assistant_plan=plan, assistant_plan_method=method, assistant_planned_at=datetime.now().isoformat())
        if opponents:
            h["opponent_plan"] = [str(o) for o in opponents]
        else:
            h.pop("opponent_plan", None)
        _write(path, data)
        return list(plan)


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
    #: query | group | schedule | env | study | settings | user (the human chose it; see hani2.choices)
    source: str = "settings"
    pool: list[str] = field(default_factory=list)
    error: str | None = None
    #: the scheduling method that picked ``spec`` ("external" for schedule.json, "" for an explicit choice)
    scheduling: str = ""
    #: the human has used every Assistant left in the pool and the study does not repeat them
    #: (``scheduling.assistant_repeats``): they finish early (see :func:`assistants_used_up`)
    exhausted: bool = False

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


def group_file(session: Any):
    """The group file the page's ``?group=`` names (``None``: none, or an admin's ``?assistants=`` wins)."""
    q = getattr(session, "query", None) or {}
    gkey = _query_val(q, "group")
    if not gkey:
        return None
    return groups.find_file(groups.OPPONENT, gkey, getattr(session, "study_ref", None))


def group_assistant(session: Any) -> str | None:
    """The Assistant the page's group file names (a spec, or ``none``), else ``None``. It always wins:
    over the study's pool, its scheduling and balance, the participant's own pick and the settings'
    on/off switch (an invitation plays with exactly the inviter's Assistant)."""
    if getattr(session, "is_admin", False) and _items(_query_val(getattr(session, "query", None) or {},
                                                                  "assistants", "assistant")):
        return None
    g = group_file(session)
    if g is None or g.error or not g.assistant:
        return None
    items = _items(g.assistant)
    return items[0] if len(items) == 1 else None


def group_agents(session: Any) -> list[str]:
    """The opponents the page's group file names (``[]``: none). They are the whole opponent pool:
    the participant cannot pick another one."""
    g = group_file(session)
    return list(g.members) if g is not None and not g.error else []


def group_people_only(session: Any) -> bool:
    """Whether the page's group file says ``"ai_fallback": false``: its sessions never get an AI
    opponent (no wait-time fallback, no "play an AI" button or choice screen, no AI pick). An
    admin's ``?opponents=`` replaces the group's pool and so its switch too."""
    if getattr(session, "is_admin", False) and _query_val(getattr(session, "query", None) or {},
                                                          "opponents", "agents"):
        return False
    g = group_file(session)
    return g is not None and not g.ai_fallback


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

        with open(Path(path) / "results.csv", newline="", encoding="utf-8") as fh:
            return max(0, sum(1 for _ in csv.reader(fh)) - 1)
    except (OSError, TypeError):
        return int(getattr(session, "round_number", 0) or 0)


def _assistant_slot(session: Any) -> int:
    """The counted negotiation the next Assistant is for: a study participant's counted rounds
    (a practice round counts as slot 0), else the human's finished negotiations."""
    st = getattr(session, "study", None)
    counted = getattr(st, "counted", None)
    if callable(counted):
        practice = getattr(st, "is_practice_next", None)
        return 0 if callable(practice) and practice() else int(counted())
    return _negotiations_done(session)


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
        if raw is None:  # a Paired HAN study plays without Assistants (see hani2.study_modes)
            info = getattr(session, "study_mode_info", None)
            raw = info.filled.get("assistants") if info is not None else None
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

    fixed = group_assistant(session)
    if fixed:  # the group file's Assistant (an invitation, a test link): nothing replaces it
        return AssistantChoice(spec=fixed, group=_query_val(session.query or {}, "group").lstrip(":"),
                               source="group", pool=[fixed])
    chosen = (getattr(session, "__dict__", None) or {}).get("chosen_assistant")
    if chosen:  # the human's own pick for this negotiation (see hani2.choices): used as given, not recorded
        return AssistantChoice(spec=str(chosen), source="user", pool=[str(chosen)], scheduling="user")
    c = assistant_pool(session, settings, plan)
    paired = (getattr(session, "__dict__", None) or {}).get("_paired_assistant")
    if paired:  # a Paired study chose it at pairing (the host's commit, the joiner's late binding)
        c.spec, c.error = str(paired), None
        c.scheduling = "external" if c.source == "schedule" else _assistant_method(session)
        if paired not in c.pool:
            c.pool = [*c.pool, str(paired)]
        return c
    if c.error or not c.pool:
        return c
    if c.source in ("query", "schedule", "fixed") or (c.source == "group" and len(c.pool) == 1):
        # an explicit choice (an admin's URL, the outside system's schedule, a test link's group
        # file naming one Assistant): used as given, not recorded
        c.spec = c.pool[0]
        c.scheduling = "external" if c.source == "schedule" else ""
        if c.source == "schedule" and _schedule_repeats(session, c.spec):
            c.scheduling = "external" + scheduling.REPEAT_SUFFIX
        return c
    method = _assistant_method(session)
    c.scheduling = method
    if method in scheduling.PER_NEGOTIATION_ASSISTANTS:
        if method == "random_each":
            c.spec = c.pool[0] if len(c.pool) == 1 else \
                scheduling.pick_assistant_slot(method, c.pool, 0, _negotiations_done(session), _seed(session))
            return c
        slot = _assistant_slot(session)
        wrap = assistants_wrap(session, method, c.pool)
        if wrap:
            _warn_repeats(session, method, c.pool)
        seq = _planned_sequence(session, c.pool, method, _plan_size(session))
        c.spec = scheduling.next_unused(seq, slot, played_assistants(session), c.pool, wrap=wrap)
        if c.spec is None:  # the pool shrank: every Assistant left in it was used by this human
            c.exhausted = True
            c.error = out_of_assistants_text(session, c.pool)
        return c
    c.spec = assign_assistant(session, c.pool, c.group, method)
    return c


def out_of_assistants_text(session: Any, pool: list[str]) -> str:
    """Why a human finishes early: every Assistant left in the pool was already used by them."""
    used = played_assistants(session)
    return (f"{getattr(session, 'user', '')} has used every Assistant left in the study's pool "
            f"({', '.join(pool) or 'none'}) after {len(used)} of {_plan_size(session)} negotiations; each "
            "Assistant is used at most once per person (scheduling.assistant_repeats is not true), so "
            "they finish early")


def assistants_used_up(session: "NegotiationSession", settings: dict | None, plan: dict | None = None) -> str | None:
    """Why the human's study ends before K negotiations because no unused Assistant is left for
    them (``None``: one is left, or the study does not plan Assistants per negotiation). This
    happens only when the pool shrank during the study and ``assistant_repeats`` is not ``true``."""
    if settings is None or getattr(session, "study_ref", None) is None:
        return None
    try:
        c = choose_assistant(session, settings, plan)
    except Exception:  # noqa: BLE001
        return None
    return c.error if c.exhausted else None


def log_finished_early(session: Any, reason: str, value: dict | None = None) -> None:
    """A human finishes the study before K negotiations because no Assistant is left for them: a
    log line and a ``WARNING`` event (``action = finished_early``), once per human and study."""
    ref = getattr(session, "study_ref", None)
    key = f"early|{store_path(ref) if ref is not None else ''}|{getattr(session, 'user', '')}"
    if key in _REPEAT_WARNED:
        return
    _REPEAT_WARNED.add(key)
    print(f"[hani2] WARNING: study {ref}: {reason}")
    try:
        from hani2 import events as ev

        ev.log_event(session.sid, ev.EventType.WARNING, user=session.user, component="scheduling",
                     action="finished_early", value={**(value or {}), "reason": reason})
    except Exception:  # noqa: BLE001
        pass


_REPEAT_WARNED: set[str] = set()


def _warn_repeats(session: Any, method: str, pool: list[str]) -> None:
    """A running study whose files break "each Assistant at most once" (K > N without
    ``assistant_repeats: true``): a warning in the log, once per study and pool; the Assistants wrap."""
    from hani2 import scheduling

    ref = getattr(session, "study_ref", None)
    if ref is None or method not in scheduling.AT_MOST_ONCE_ASSISTANTS:
        return
    probs = scheduling.repeat_problems(method, _plan_size(session), pool, scheduling.options_for(ref))
    for p in probs:
        key = f"{ref}|{p}"
        if key not in _REPEAT_WARNED:
            _REPEAT_WARNED.add(key)
            print(f"[hani2] WARNING: study {ref}: {p} (the Assistants wrap around)")


def _schedule_repeats(session: Any, spec: str) -> bool:
    """Whether the outside schedule's slot for this negotiation names ``spec`` and an earlier counted
    slot names it too (an ``external:repeat`` error); logged as an ``ERROR`` event. Only per-slot
    ``assistant`` entries count (a top-level ``assistant`` is one Assistant for every negotiation),
    and only when the study's method promises each Assistant at most once and
    ``assistant_repeats`` is not ``true``."""
    from hani2 import scheduling

    st = getattr(session, "study", None)
    if not callable(getattr(st, "schedule", None)) or not callable(getattr(st, "is_practice_next", None)) \
            or st.is_practice_next():
        return False
    ref = getattr(session, "study_ref", None)
    if ref is None or scheduling.repeats_allowed(_assistant_method(session), scheduling.options_for(ref)):
        return False
    slot = _assistant_slot(session)
    try:
        sched = st.schedule()
    except Exception:  # noqa: BLE001
        return False

    def named(j: int) -> str:
        e = sched[j] if 0 <= j < len(sched) and isinstance(sched[j], dict) else {}
        return str(e.get("assistant") or "")

    if named(slot) != spec or spec not in {named(j) for j in range(slot)}:
        return False
    msg = (f"schedule.json names the Assistant {spec!r} again for {session.user}'s negotiation {slot + 1}; "
           "each Assistant should be used at most once per person (set scheduling.assistant_repeats: true "
           "to allow it). It is used as written")
    key = f"{ref}|{session.user}|{slot}"
    if key not in _REPEAT_WARNED:
        _REPEAT_WARNED.add(key)
        print(f"[hani2] ERROR: {msg}")
        try:
            from hani2 import events as ev

            ev.log_event(session.sid, ev.EventType.ERROR, user=session.user, component="scheduling",
                         action="scheduling_repeat", value={"assistant": spec, "slot": slot, "error": msg})
        except Exception:  # noqa: BLE001
            pass
    return True


# --------------------------------------------------------------------------- #
# Paired studies: match cells and the Assistants a person has used             #
# --------------------------------------------------------------------------- #
#: the cell store of a study, next to ``assignments.json`` and under the same locks
CELLS_FILE = "match_cells.json"
#: an in-flight match older than its time limit plus this many seconds is dropped
INFLIGHT_GRACE = 600.0


def cells_path(ref: Any = projects.UNSET) -> Path:
    """``match_cells.json`` of study ``ref`` (default: the current study)."""
    return store_path(ref).with_name(CELLS_FILE)


def _empty_cells() -> dict[str, Any]:
    return {"version": 1, "cells": {}, "inflight": {}, "positions": {}}


def _read_cells(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k in ("cells", "inflight", "positions"):
                if not isinstance(data.get(k), dict):
                    data[k] = {}
            data.setdefault("version", 1)
        else:
            data = _empty_cells()
    except FileNotFoundError:
        data = _empty_cells()
    except Exception as e:  # noqa: BLE001
        print(f"[hani2] {path} is broken ({e}); starting a new one next to it")
        try:
            path.replace(path.with_name(path.name + f".broken-{int(datetime.now().timestamp())}"))
        except OSError:
            pass
        data = _empty_cells()
    now = datetime.now().timestamp()
    for mid, e in list(data["inflight"].items()):  # stale: older than the time limit + INFLIGHT_GRACE
        try:
            if float((e or {}).get("expires") or 0) < now:
                del data["inflight"][mid]
        except (TypeError, ValueError):
            del data["inflight"][mid]
    return data


@contextlib.contextmanager
def cell_store(ref: Any, write: bool = True) -> Iterator[dict[str, Any]]:
    """The cell store of study ``ref``, read (stale in-flight entries dropped) under the lock of
    ``assignments.json``, and written back atomically when ``write`` and it changed."""
    path = store_path(ref)
    cpath = path.with_name(CELLS_FILE)
    with _locked(path):
        data = _read_cells(cpath)
        before = json.dumps(data, sort_keys=True)
        yield data
        if write and json.dumps(data, sort_keys=True) != before:
            _write(cpath, data)


def read_cells(ref: Any = projects.UNSET) -> dict[str, Any]:
    """A copy of the cell store of study ``ref`` (stale in-flight entries left out)."""
    with cell_store(ref, write=False) as data:
        return json.loads(json.dumps(data))


def _side_name(spec: Any) -> str:
    s = str(spec or "").strip()
    return s if s else NO_ASSISTANT


def cell_key(scenario: Any, a0: Any, a1: Any) -> str:
    """The canonical key of a match cell: ``"<scenario>|<A>@0|<B>@1"`` (sides by ufun index;
    ``none`` for a side without an Assistant)."""
    return f"{scenario}|{_side_name(a0)}@0|{_side_name(a1)}@1"


def parse_cell(key: str) -> tuple[str, str, str]:
    """``(scenario, side-0 Assistant, side-1 Assistant)`` of a cell key."""
    scen, _, rest = str(key).partition("|")
    left, _, right = rest.partition("|")
    return scen, left.rsplit("@", 1)[0], right.rsplit("@", 1)[0]


def cell_count(data: dict[str, Any], key: str) -> int:
    """Completed + in-flight matches of a cell."""
    done = int((data["cells"].get(key) or {}).get("completed") or 0)
    return done + sum(1 for e in data["inflight"].values() if (e or {}).get("cell") == key)


def assistant_scenario_count(data: dict[str, Any], assistant: str, scenario: str) -> int:
    """Completed + in-flight matches of ``scenario`` (a cell's scenario part, or its recorded type)
    that have ``assistant`` on either side."""

    def hit(key: str, typ: Any) -> bool:
        scen, a0, a1 = parse_cell(key)
        return (scen == scenario or str(typ or "") == scenario) and assistant in (a0, a1)

    n = sum(int(c.get("completed") or 0) for k, c in data["cells"].items() if hit(k, (c or {}).get("type")))
    return n + sum(1 for e in data["inflight"].values() if hit(str((e or {}).get("cell")), (e or {}).get("type")))


def position_count(data: dict[str, Any], assistant: str, position: int) -> int:
    """How many completed matches used ``assistant`` as a person's ``position``-th Assistant."""
    row = data["positions"].get(assistant) or []
    return int(row[position]) if 0 <= position < len(row) else 0


def reserve_cell(data: dict[str, Any], match_id: str, key: str, *, scenario_type: str = "",
                 sides: dict[int, tuple[str, int | None]] | None = None, ttl: float | None = None) -> None:
    """Put match ``match_id`` in flight in cell ``key`` (call inside :func:`cell_store`)."""
    now = datetime.now()
    limit = float(ttl) if ttl and ttl != float("inf") else 3600.0
    data["inflight"][match_id] = {
        "cell": key, "type": scenario_type, "since": now.isoformat(timespec="seconds"),
        "expires": now.timestamp() + limit + INFLIGHT_GRACE,
        "sides": {str(i): [a, k] for i, (a, k) in (sides or {}).items()}, "rows": {},
    }


def release_cell(ref: Any, match_id: str) -> bool:
    """Drop the in-flight entry of ``match_id`` (separated before the start, abandoned, erred)."""
    if ref is None or not match_id:
        return False
    with cell_store(ref) as data:
        return data["inflight"].pop(match_id, None) is not None


def cell_row_written(ref: Any, match_id: str, side: int, ok: bool) -> str:
    """One side's row of match ``match_id`` was written (``ok``: not abandoned, not erred). The
    cell is filled once both sides wrote a clean row; a row that is not clean releases it. Returns
    ``completed``, ``released``, ``waiting`` or ``""`` (no in-flight entry: nothing to do)."""
    if ref is None or not match_id:
        return ""
    with cell_store(ref) as data:
        e = data["inflight"].get(match_id)
        if e is None:
            return ""
        if not ok:
            del data["inflight"][match_id]
            return "released"
        e.setdefault("rows", {})[str(side)] = True
        if len(e["rows"]) < 2:
            return "waiting"
        del data["inflight"][match_id]
        key = str(e.get("cell"))
        c = data["cells"].setdefault(key, {"completed": 0, "match_ids": []})
        if e.get("type"):
            c["type"] = e["type"]
        if match_id not in c.setdefault("match_ids", []):
            c["completed"] = int(c.get("completed") or 0) + 1
            c["match_ids"].append(match_id)
            for a, k in (e.get("sides") or {}).values():
                if not a or k is None or is_no_assistant(a):
                    continue
                row = data["positions"].setdefault(a, [])
                while len(row) <= int(k):
                    row.append(0)
                row[int(k)] += 1
        return "completed"


def used_assistants(session: Any) -> list[str]:
    """The Assistants the session's human has used in this study (a negotiation with them started),
    in order; ``[]`` for admins and guests (theirs are kept on the session)."""
    if not counts_as_human(session):
        return [a for a, _m in (getattr(session, "__dict__", {}).get("_uncounted_used") or [])]
    data = read_assignments(session.study_ref)
    h = data["humans"].get(session.user) or {}
    return [str(x[0]) for x in h.get("used_assistants") or [] if isinstance(x, (list, tuple)) and x]


def skipped_assistants(session: Any) -> list[str]:
    """The Assistants skipped for the human because nobody could be paired with them
    (``pairing.fallback: end``)."""
    if not counts_as_human(session):
        return list(getattr(session, "__dict__", {}).get("_uncounted_skipped") or [])
    data = read_assignments(session.study_ref)
    return list((data["humans"].get(session.user) or {}).get("skipped_assistants") or [])


def mark_used(session: Any, assistant: str, match_id: str) -> None:
    """Record that the human started a negotiation with ``assistant`` (``used_assistants``, as
    ``[assistant, match_id]``; once per match)."""
    if not assistant or is_no_assistant(assistant):
        return
    if not counts_as_human(session):
        lst = session.__dict__.setdefault("_uncounted_used", [])
        if not any(m == match_id for _a, m in lst):
            lst.append((assistant, match_id))
        return
    path = store_path(session.study_ref)
    cross = _explicit_cross(session.study_ref)
    with _locked(path):
        data = _read(path)
        h = _human(data, session.user, cross)
        lst = h.setdefault("used_assistants", [])
        if any(isinstance(x, (list, tuple)) and len(x) > 1 and x[1] == match_id for x in lst):
            return
        lst.append([assistant, match_id])
        _write(path, data)


def skip_assistant(session: Any, assistant: str) -> None:
    """Nobody could be paired with the human's ``assistant`` (``pairing.fallback: end``): it is
    left out of their remaining Assistants (and not counted as used)."""
    if not assistant:
        return
    if not counts_as_human(session):
        session.__dict__.setdefault("_uncounted_skipped", []).append(assistant)
        return
    path = store_path(session.study_ref)
    with _locked(path):
        data = _read(path)
        h = _human(data, session.user, _explicit_cross(session.study_ref))
        h.setdefault("skipped_assistants", []).append(assistant)
        _write(path, data)


def _schedule_set(session: Any) -> list[str]:
    """The Assistants of every slot of the human's ``schedule.json`` (``external`` in Paired: a set)."""
    st = getattr(session, "study", None)
    out: list[str] = []
    try:
        for e in (st.schedule() if callable(getattr(st, "schedule", None)) else []):
            if isinstance(e, dict) and e.get("assistant"):
                out.append(str(e["assistant"]))
        data = st.schedule_data() if callable(getattr(st, "schedule_data", None)) else None
        if not out and isinstance(data, dict) and data.get("assistant"):
            out.append(str(data["assistant"]))
    except Exception:  # noqa: BLE001
        return []
    return out


def _dedupe(seq: list[str]) -> list[str]:
    return list(dict.fromkeys(seq))


def remaining_assistants(session: "NegotiationSession", settings: dict, plan: dict | None = None) -> tuple[list[str], str]:
    """``(R_u, method)``: the Assistants the human may still play in a Paired study, in the order of
    preference, and the scheduling method they come from (see the Study management docs):

    * an Assistant that is fixed for this page (the group file's, the human's own pick, an admin's
      URL) or the study's one-per-person methods (``balanced``, ``random_fixed``, ``round_robin``):
      that one Assistant, for every match;
    * ``latin_square`` / ``cyclic`` / ``balanced_subset`` / ``random_subset``: the first K of the
      human's sequence, without the ones already used (or skipped); with
      ``scheduling.assistant_repeats: true`` the sequence wraps instead;
    * ``random_each``: the whole pool (repeats allowed);
    * ``external`` (or a ``schedule.json`` naming Assistants): the Assistants of its slots, as a set.

    ``[]`` means the human has used every Assistant planned for them, except with the method
    ``"error"``: the pool could not be read (the error is shown when the Assistant is built).
    """
    from hani2 import scheduling

    fixed = group_assistant(session)
    if fixed:
        return [fixed], ""
    chosen = (getattr(session, "__dict__", None) or {}).get("chosen_assistant")
    if chosen:
        return [str(chosen)], "user"
    c = assistant_pool(session, settings, plan)
    if c.error or not c.pool:
        return [], "error"  # not "used up": the Assistant's error is shown as usual
    if c.source in ("query", "fixed") or (c.source == "group" and len(c.pool) == 1):
        return [c.pool[0]], ""
    method = _assistant_method(session)
    used = set(played_assistants(session)) | set(skipped_assistants(session))
    ref = getattr(session, "study_ref", None)
    options = scheduling.options_for(ref) if ref is not None else {}
    if c.source == "schedule" or method == "external":
        seq = _schedule_set(session) or list(c.pool)
        if scheduling.repeats_allowed("external", options):
            return _dedupe(seq), "external"
        return [a for a in _dedupe(seq) if a not in used], "external"
    if method not in scheduling.PER_NEGOTIATION_ASSISTANTS:
        return [assign_assistant(session, c.pool, c.group, method)], method
    if method == "random_each":
        order = list(c.pool)
        scheduling.rng(_seed(session), "paired", len(used)).shuffle(order)
        return order, method
    k = _plan_size(session)
    seq = _planned_sequence(session, c.pool, method, k)
    skipped = set(skipped_assistants(session))
    if assistants_wrap(session, method, c.pool, paired=True):
        n = len(used_assistants(session))
        rot = seq[n % len(seq):] + seq[:n % len(seq)] if seq else []
        return [a for a in _dedupe(rot) if a not in skipped and a in c.pool], method
    # each Assistant at most once: the open slots, filled from Assistants not used (or skipped) yet,
    # also after a member left the pool (then the plan is made again around the used ones)
    taken = set(played_assistants(session)) | skipped
    rest = scheduling.fill_open_slots(seq, taken, c.pool, k, start=len(taken))
    pos = {a: i for i, a in enumerate(_dedupe(seq))}
    return sorted(rest, key=lambda a: pos.get(a, len(pos))), method
