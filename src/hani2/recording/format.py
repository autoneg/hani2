"""The recording file format (``.hrec``) and its reader.

A recording is a sequence of JSON objects, one per line, gzip-compressed once
the recording is finished (``<name>.hrec``). While it is being written it is a
plain, line-flushed JSON-lines file (``<name>.hrec.jsonl``) so an abandoned
session still loads; the reader accepts both.

Line 1 is the header::

    {"k": "header", "format": "hani2-recording", "version": 1, "id": ..., "t0": <epoch s>, ...}

Every other line is an event with ``t`` (seconds since ``t0``) and ``k`` (kind):

======== ===================================================================
``out``  a message the server sent to the browser (``m``: its type, ``seq``)
         — ``state`` messages are stored as a full keyframe (``full``) or as
         a delta (``delta``) against the previous state; ``tool`` views the
         same way (``full`` / ``delta``) per tool id; any other message as
         ``msg``.
``in``   a message the browser sent (``msg``) — every click on a button
         that does something arrives here.
``tel``  a batch of client telemetry (``sent``: client epoch ms when the
         batch was sent, ``ev``: ``[[client epoch ms, type, ...], ...]``) —
         mouse moves, clicks, keys, scrolls, focus, visibility, viewport,
         local UI state, received message sequence numbers, checkpoints.
``ev``   a semantic event (offer made, tool opened, …) — ``type`` and the
         fields of :func:`hani2.events.log_event`.
``act``  an action executed on the participant's seat (``actor``: human,
         agent or autopilot; ``type``: offer, accept, end or text).
``draft`` the counter-offer draft changed (``by``: human or agent).
``chat`` a message in the assistant chat.
``llm``  one language-model call (``role``, ``model``, ``latency``, tokens,
         cost, the new prompt messages and the response).
``fn``   a function the support agent called (``name``, ``args``, ``result``).
``scenario`` the scenario (issues, every ufun as a utility table, reserved
         values) — metrics are computed from the file alone.
``start`` / ``trace`` / ``result`` / ``questionnaire`` / ``end``.
======== ===================================================================

Deltas (:func:`diff` / :func:`patch`) map a key to ``{"s": value}`` (set),
``{"a": [items]}`` (append to a list), ``{"d": 1}`` (delete) or ``{"o":
delta}`` (a nested delta).
"""

from __future__ import annotations

import copy
import gzip
import io
import json
import zlib
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

FORMAT = "hani2-recording"
VERSION = 1
SUFFIX = ".hrec"
PARTIAL_SUFFIX = ".hrec.jsonl"
#: a full state keyframe is written every this many state messages
KEYFRAME_EVERY = 40

_MISSING = object()


# --------------------------------------------------------------------------- #
# Deltas                                                                       #
# --------------------------------------------------------------------------- #
def diff(old: Any, new: Any) -> dict | None:
    """The delta that turns dict ``old`` into dict ``new`` (``None`` if equal)."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise TypeError("diff works on dicts")
    out: dict[str, Any] = {}
    for k, v in new.items():
        o = old.get(k, _MISSING)
        if o is _MISSING:
            out[k] = {"s": v}
        elif _same(o, v):
            continue
        elif isinstance(o, dict) and isinstance(v, dict):
            d = diff(o, v)
            if d:
                out[k] = {"o": d}
        elif isinstance(o, list) and isinstance(v, list) and len(v) > len(o) and _same(v[: len(o)], o):
            out[k] = {"a": v[len(o):]}
        else:
            out[k] = {"s": v}
    for k in old:
        if k not in new:
            out[k] = {"d": 1}
    return out or None


def _same(a: Any, b: Any) -> bool:
    """Equality that tells ``True`` from ``1`` (JSON does)."""
    if type(a) is not type(b) and (isinstance(a, bool) or isinstance(b, bool)):
        return False
    if isinstance(a, (dict, list)):
        return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    return a == b


def patch(old: dict, delta: dict | None) -> dict:
    """Apply a :func:`diff` delta; returns a new dict (``old`` is not changed)."""
    if not delta:
        return old
    new = dict(old)
    for k, op in delta.items():
        if "s" in op:
            new[k] = op["s"]
        elif "a" in op:
            new[k] = list(new.get(k) or []) + list(op["a"])
        elif "o" in op:
            base = new.get(k)
            new[k] = patch(base if isinstance(base, dict) else {}, op["o"])
        elif "d" in op:
            new.pop(k, None)
    return new


# --------------------------------------------------------------------------- #
# Reading files                                                                #
# --------------------------------------------------------------------------- #
def _lines(path: Path) -> Iterator[str]:
    """Lines of a (possibly truncated) gzip or plain JSON-lines file."""
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        try:
            text = gzip.decompress(raw).decode("utf-8")
        except (EOFError, OSError, zlib.error):
            # truncated: decompress what is there
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
            try:
                text = d.decompress(raw).decode("utf-8", errors="replace")
            except zlib.error:
                text = ""
    else:
        text = raw.decode("utf-8", errors="replace")
    for line in io.StringIO(text):
        if line.strip():
            yield line


def read_records(path: str | Path) -> list[dict]:
    """Every record in a recording file (a broken last line is skipped)."""
    out = []
    for line in _lines(Path(path)):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def is_recording(path: Path) -> bool:
    return path.name.endswith(SUFFIX) or path.name.endswith(PARTIAL_SUFFIX)


def recording_id(path: Path) -> str:
    n = path.name
    for s in (PARTIAL_SUFFIX, SUFFIX):
        if n.endswith(s):
            return n[: -len(s)]
    return path.stem


# --------------------------------------------------------------------------- #
# The loaded recording                                                         #
# --------------------------------------------------------------------------- #
@dataclass
class Recording:
    """A loaded recording with helpers used by the metrics and the player."""

    path: Path | None
    header: dict
    events: list[dict]
    _states: list[tuple[float, int, dict]] | None = field(default=None, repr=False)

    # -- loading -----------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "Recording":
        p = Path(path)
        recs = read_records(p)
        if not recs or recs[0].get("k") != "header" or recs[0].get("format") != FORMAT:
            raise ValueError(f"{p} is not a {FORMAT} file")
        return cls(p, recs[0], recs[1:])

    @classmethod
    def from_records(cls, records: list[dict]) -> "Recording":
        return cls(None, records[0], records[1:])

    @property
    def id(self) -> str:
        return str(self.header.get("id") or (recording_id(self.path) if self.path else ""))

    @property
    def complete(self) -> bool:
        return any(e.get("k") == "end" for e in self.events)

    @property
    def duration(self) -> float:
        return float(self.events[-1]["t"]) if self.events else 0.0

    def of(self, *kinds: str) -> list[dict]:
        return [e for e in self.events if e.get("k") in kinds]

    def first(self, kind: str) -> dict | None:
        for e in self.events:
            if e.get("k") == kind:
                return e
        return None

    def last(self, kind: str) -> dict | None:
        for e in reversed(self.events):
            if e.get("k") == kind:
                return e
        return None

    # -- semantic accessors ----------------------------------------------------------
    @property
    def scenario(self) -> dict | None:
        return self.last("scenario")

    @property
    def result(self) -> dict | None:
        r = self.last("result")
        return r.get("row") if r else None

    @property
    def summary(self) -> dict | None:
        r = self.last("result")
        return r.get("summary") if r else None

    @property
    def trace(self) -> list[dict]:
        r = self.last("trace")
        return list(r.get("rows") or []) if r else []

    @property
    def start(self) -> dict | None:
        return self.first("start")

    @property
    def questionnaire(self) -> dict | None:
        return self.last("questionnaire")

    def offers(self) -> list[dict]:
        """Offers in order: ``{"t", "by": "human"|"agent", "offer", "step", "text"}``
        (from the trace when there is one, else from the actions)."""
        sc = self.scenario or {}
        human_id = str((self.start or {}).get("human_id") or sc.get("human_id") or "")
        rows = self.trace
        out = []
        if rows:
            for r in rows:
                if r.get("offer") is None:
                    continue
                out.append(dict(t=r.get("t"), by="human" if str(r.get("negotiator")) == human_id else "agent",
                                offer=r["offer"], step=r.get("step"), text=r.get("text")))
            return out
        # no trace (the session was abandoned mid-negotiation): the human side's
        # actions and the partner offers shown in the history
        names = sc.get("issue_names") or []
        seen: set[int] = set()
        items = [(float(a["t"]), dict(t=a["t"], by="human", offer=a.get("offer"), step=a.get("step"), text=a.get("text")))
                 for a in self.of("act") if a.get("type") == "offer" and a.get("offer") is not None]
        for t, _, st in self.states():
            for h in (st or {}).get("history") or []:
                if h.get("kind") == "offer" and h.get("by") == "agent" and h.get("offer") and h.get("id") not in seen:
                    seen.add(h.get("id"))
                    items.append((t, dict(t=t, by="agent", offer=[h["offer"].get(n) for n in names],
                                          step=h.get("step"), text=h.get("text"))))
        items.sort(key=lambda x: x[0])
        out = [o for _, o in items]
        return out

    def telemetry(self) -> list[tuple[float, str, list]]:
        """Client telemetry as ``(t, type, payload)`` on the recording clock."""
        out = []
        for e in self.of("tel"):
            sent = float(e.get("sent") or 0)
            for item in e.get("ev") or []:
                if not item or len(item) < 2:
                    continue
                ct, typ = item[0], item[1]
                t = float(e["t"]) + (float(ct) - sent) / 1000.0 if sent else float(e["t"])
                out.append((max(0.0, t), str(typ), list(item[2:])))
        out.sort(key=lambda x: x[0])
        return out

    # -- reconstructing what was on screen ----------------------------------------------
    def states(self) -> list[tuple[float, int, dict]]:
        """Every state the browser received: ``(t, seq, state)``."""
        if self._states is None:
            cur: dict = {}
            out = []
            for e in self.events:
                if e.get("k") != "out" or e.get("m") != "state":
                    continue
                if "full" in e:
                    cur = e["full"]
                else:
                    cur = patch(cur, e.get("delta"))
                out.append((float(e["t"]), int(e.get("seq", -1)), cur))
            self._states = out
        return self._states

    def state_at(self, t: float) -> dict | None:
        st = self.states()
        i = bisect_right([x[0] for x in st], t) - 1
        return copy.deepcopy(st[i][2]) if i >= 0 else None

    def tool_views(self) -> list[tuple[float, int, str, Any]]:
        cur: dict[str, Any] = {}
        out = []
        for e in self.events:
            if e.get("k") != "out" or e.get("m") != "tool":
                continue
            tid = str(e.get("id"))
            if "full" in e:
                v = e["full"]
            else:
                v = patch(cur.get(tid) or {}, e.get("delta"))
            cur[tid] = v
            out.append((float(e["t"]), int(e.get("seq", -1)), tid, v))
        return out

    def to_json(self) -> dict:
        return {"header": self.header, "events": self.events}


def iter_recordings(root: str | Path) -> Iterator[Path]:
    """Every recording file under ``root`` (a file or a directory, recursively)."""
    p = Path(root).expanduser()
    if p.is_file():
        if is_recording(p):
            yield p
        return
    if not p.is_dir():
        return
    for f in sorted(p.rglob("*")):
        if f.is_file() and is_recording(f):
            yield f


def dumps_line(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=str)
